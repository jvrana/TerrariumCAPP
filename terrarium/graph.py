import networkx as nx
import json
from terrarium.utils import validate_with_schema
from terrarium.exceptions import SchemaValidationError


class GraphBase(object):
    def __init__(self, name=None, graph_class=nx.DiGraph, graph=None):
        self._graph = None
        if graph is not None:
            graph_class = graph.__class__
        self.graph = graph_class()
        self.graph.name = name

    @property
    def meta(self):
        return self.graph.graph

    @property
    def graph(self):
        return self._graph

    @graph.setter
    def graph(self, g):
        self._graph = g
        self._init_graph()

    def _init_graph(self):
        self._graph.graph.update(self.meta)

    @property
    def name(self):
        return self.graph.name

    @name.setter
    def name(self, n):
        self.graph.name = n

    @property
    def nodes(self):
        return self.graph.nodes

    @property
    def edges(self):
        return self.graph.edges

    def get_node(self, n):
        return self.graph.nodes[n]

    def get_edge(self, n1, n2):
        return self.graph[n1][n2]

    def add_edge(self, n1, n2, **kwargs):
        assert n1 in self.graph
        assert n2 in self.graph
        self.graph.add_edge(n1, n2, **kwargs)

    def add_node(self, n, **kwargs):
        self.graph.add_node(n, **kwargs)

    def copy(self):
        return self.__copy__()

    @staticmethod
    def nx_shallow_copy(graph):
        graph_copy = graph.__class__()
        graph_copy.graph = dict(graph.graph)
        return graph_copy

    @classmethod
    def nx_copy(cls, graph):
        graph_copy = cls.nx_shallow_copy(graph)
        graph_copy.add_nodes_from(graph.nodes(data=True))
        graph_copy.add_edges_from(graph.edges(data=True))
        return graph_copy

    @classmethod
    def nx_subgraph(cls, graph, nbunch):
        graph_copy = cls.nx_shallow_copy(graph)
        graph_copy.add_nodes_from((n, graph.nodes[n]) for n in nbunch)
        edges = []
        for n1, n2 in graph.edges:
            if n1 in nbunch and n2 in nbunch:
                edges.append((n1, n2, graph.edges[n1, n2]))
        graph_copy.add_edges_from(edges)
        return graph_copy

    def json(self):
        self._init_graph()
        return nx.adjacency_data(self.graph)

    def subgraph(self, nbunch):
        copied = self.shallow_copy()
        copied.graph = self.nx_subgraph(self.graph, nbunch)
        return copied

    @classmethod
    def load(cls, json_data):
        graph = nx.adjacency_graph(json_data)
        model_graph = cls()
        model_graph.graph = graph
        return model_graph

    def write(self, path):
        with open(path, "w") as f:
            json.dump(self.json(), f)

    @classmethod
    def read(cls, path):
        with open(path, "r") as f:
            return cls.load(json.load(f))

    def save_gexf(self, path):
        return nx.write_gexf(self.graph, path)

    @classmethod
    def load_gexf(cls, path, prefix="", suffix=""):
        graph = nx.read_gexf(path)
        model_graph = cls()
        model_graph.graph = graph
        model_graph.prefix = prefix
        model_graph.suffix = suffix
        return model_graph

    def shallow_copy(self):
        return self.__class__(name=self.name, graph_class=self.graph.__class__)

    def __contains__(self, item):
        return item in self.graph

    def __len__(self):
        return self.graph.number_of_nodes()

    def __copy__(self):
        copy = self.shallow_copy()
        copy.graph = self.nx_copy(self.graph)
        return copy


class MapperGraph(GraphBase):

    PREFIX_KEY = "__prefix__"
    SUFFIX_KEY = "__suffix__"
    DEFAULT_DATA_KEY = "__data__"
    DATA_KEY_KEY = "__data_key__"

    def __init__(
        self,
        key_func,
        value_func=None,
        data_key=None,
        name=None,
        graph_class=nx.DiGraph,
        graph=None,
    ):
        self.value_func = value_func
        self.key_func = key_func

        super().__init__(name=name, graph_class=graph_class, graph=graph)

        if data_key is None:
            data_key = self.DEFAULT_DATA_KEY
        self.meta[self.DATA_KEY_KEY] = data_key
        self.prefix = ""
        self.suffix = ""

    @property
    def prefix(self):
        return self.meta[self.PREFIX_KEY]

    @prefix.setter
    def prefix(self, p):
        self.meta[self.PREFIX_KEY] = p

    @property
    def suffix(self):
        return self.meta[self.SUFFIX_KEY]

    @suffix.setter
    def suffix(self, s):
        self.meta[self.SUFFIX_KEY] = s

    @property
    def data_key(self):
        return self.meta[self.DATA_KEY_KEY]

    def add_prefix(self, prefix):
        """Sets this graph to have a prefix."""
        mapping = {n: prefix + n for n in self.nodes}
        self.graph = nx.relabel_nodes(self.graph, mapping)
        self.prefix = prefix

    def add_suffix(self, suffix):
        mapping = {n: n + suffix for n in self.nodes}
        self.graph = nx.relabel_nodes(self.graph, mapping)
        self.suffix = suffix

    def key(self, data):
        return self.key_func(data)

    def value(self, data):
        if self.value_func:
            return self.value_func(data)
        return data

    def node_id(self, data):
        s = self.key(data)
        return self.prefix + s + self.suffix

    def add_data(self, model_data):
        self.add_node(self.node_id(model_data), **{self.data_key: model_data})

    def get_data(self, node_id):
        return self.graph.nodes[node_id][self.data_key]

    def node_data(self):
        return self.graph.nodes(data=self.data_key)

    def add_edge_from_models(self, m1, m2, **kwargs):
        n1 = self.node_id(m1)
        n2 = self.node_id(m2)
        if n1 not in self.graph:
            self.add_data(m1)
        if n2 not in self.graph:
            self.add_data(m2)
        self.graph.add_edge(n1, n2, **kwargs)

    def shallow_copy(self):
        return self.__class__(
            key_func=self.key_func,
            value_func=self.value_func,
            data_key=self.data_key,
            name=self.name,
            graph_class=self.graph.__class__,
        )


class SchemaGraph(MapperGraph):
    def __init__(
        self,
        key_func,
        value_func=None,
        data_key=None,
        schemas=None,
        name=None,
        graph_class=nx.DiGraph,
        graph=None,
    ):
        if schemas is None:
            schemas = []
        self.schemas = schemas
        super().__init__(
            key_func=key_func,
            value_func=value_func,
            data_key=data_key,
            name=name,
            graph_class=graph_class,
            graph=graph,
        )

    def _init_graph(self):
        super()._init_graph()
        self.validate(raises=True)

    def validate(self, raises=False):
        valid = True
        if self.schemas:
            for n, ndata in self.graph.nodes(data=self.data_key):
                if not any(
                    validate_with_schema(ndata, schema) for schema in self.schemas
                ):
                    valid = False
                    break
        if raises and not valid:
            raise SchemaValidationError("Graph has invalid data.")
        return valid

    def validate_data(self, data, raises=False):
        valid = True
        if self.schemas:
            valid = any(validate_with_schema(data, schema) for schema in self.schemas)
            if raises and not valid:
                raise SchemaValidationError("Data is invalid for {}".format(self))
        return valid

    def add_data(self, model_data):
        self.validate_data(model_data, raises=True)
        super().add_data(model_data)

    def get_data(self, node_id):
        return self.graph.nodes[node_id][self.data_key]

    def get_edge(self, n1, n2):
        return self.graph[n1][n2]

    def add_edge(self, n1, n2, **kwargs):
        assert n1 in self.graph
        assert n2 in self.graph
        self.graph.add_edge(n1, n2, **kwargs)

    def add_edge_from_models(self, m1, m2, **kwargs):
        n1 = self.node_id(m1)
        n2 = self.node_id(m2)
        if n1 not in self.graph:
            self.add_data(m1)
        if n2 not in self.graph:
            self.add_data(m2)
        self.graph.add_edge(n1, n2, **kwargs)

    def shallow_copy(self):
        return self.__class__(
            self.key_func,
            value_func=self.value_func,
            data_key=self.data_key,
            schemas=list(self.schemas),
            name=self.name,
            graph_class=self.graph.__class__,
        )


class ModelGraph(SchemaGraph):
    def __init__(self, name=None, graph=None):
        model_id = lambda data: "{}_{}".format(data["__class__"], data["primary_key"])
        super().__init__(model_id, name=name, graph=graph)
        self.schemas.append({"__class__": str, "primary_key": int})

    def shallow_copy(self):
        return self.__class__(name=self.name)
