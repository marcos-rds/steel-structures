"""Topology public API kept separate from preset generators."""
from .models import TopologyNode, TopologyEdge, TopologyGraph
from .patterns import generate_topology

__all__ = ["TopologyNode", "TopologyEdge", "TopologyGraph", "generate_topology"]
