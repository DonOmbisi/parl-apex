"""
Connector registry
==================
Maps connector type strings (as declared in client config.yaml files) to
the async callable that runs them.

Adding a new connector means:
  1. Create connectors/<name>_connector.py
  2. Add it to CONNECTOR_REGISTRY below

Nothing else in the codebase needs to change.
"""

from connectors.erpnext_connector import ERPNextConnector

# Registry: connector type string → connector class
CONNECTOR_REGISTRY = {
    "erpnext": ERPNextConnector,
}
