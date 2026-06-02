"""Shared, dependency-light utilities used across ModelForge-Swarm.

Modules here MUST NOT import from agents, services, graph, or storage to keep
the dependency graph acyclic. They provide deterministic primitives: IDs,
hashing, time, logging, errors, and configuration.
"""
