\"\"\"Simple ensemble that averages outputs from multiple models.\"\"\"

from typing import List
from src.base_models.base_model import BaseModel


class Ensemble:
    def __init__(self, models: List[BaseModel], weights: List[float] | None = None):
        self.models = models
        self.weights = weights or [1.0] * len(models)

    def prepare(self, config: dict) -> None:
        for model in self.models:
            model.prepare(config)

    def run(self) -> None:
        for model in self.models:
            model.run()

    def aggregate_outputs(self) -> dict:
        aggregated: dict = {}
        total_weight = sum(self.weights) if self.weights else 1.0

        for weight, model in zip(self.weights, self.models):
            outputs = model.get_outputs()
            for key, value in outputs.items():
                aggregated[key] = aggregated.get(key, 0.0) + weight * value

        # normalise by total weight
        for key in aggregated:
            aggregated[key] /= total_weight

        return aggregated
