\"\"\"Base interface for models that can be combined in ensembles.\"\"\"


class BaseModel:
    def prepare(self, config: dict) -> None:
        \"\"\"Load data and parameters from config.\"\"\"
        raise NotImplementedError

    def run(self) -> None:
        \"\"\"Run the model.\"\"\"
        raise NotImplementedError

    def get_outputs(self) -> dict:
        \"\"\"Return a dict of outputs, e.g. {'yield': ..., 'soil_health': ...}.\"
        \"\"\"
        raise NotImplementedError
