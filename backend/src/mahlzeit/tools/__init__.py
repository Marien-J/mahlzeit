"""The tool registry: every operation AI clients may perform, defined once.

Exported to the Claude connector as MCP tools (M1) and to the in-app assistant (M6). Tools are
thin adapters: they validate input, call the same service functions as the REST API, and return
the same views. They act as the signed-in person with that person's permissions.
"""
