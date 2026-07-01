import os
import logging
from graph.client_graph import ClientKnowledgeGraph

logger = logging.getLogger("parl_apex.graph")

# Global registry of client graph instances
_graph_registry = {}

def get_client_graph(client_name: str, graph_path: str = None) -> ClientKnowledgeGraph:
    """
    Retrieves the ClientKnowledgeGraph instance for a client.
    Initializes a new instance if it does not already exist.
    """
    if client_name in _graph_registry:
        return _graph_registry[client_name]
    
    if not graph_path:
        raise ValueError(f"Graph path must be provided to initialize graph for client: {client_name}")
        
    logger.info(f"Registering new knowledge graph instance for client '{client_name}'")
    _graph_registry[client_name] = ClientKnowledgeGraph(graph_path)
    return _graph_registry[client_name]

def close_all_graphs():
    """
    Closes all registered knowledge graph instances to release file locks.
    """
    for client_name, graph in list(_graph_registry.items()):
        try:
            graph.close()
            logger.info(f"Closed graph for client '{client_name}'")
        except Exception as e:
            logger.error(f"Error closing graph for client '{client_name}': {e}")
    _graph_registry.clear()
