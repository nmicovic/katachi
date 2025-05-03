class InvalidNodeTypeError(ValueError):
    def __init__(self, node_type: str):
        super().__init__(f"Invalid or missing node type: {node_type}")
