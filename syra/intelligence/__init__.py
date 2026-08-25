"""Camada de inteligencia: selecao de testes e auto-otimizacao governada."""

from syra.intelligence.test_selector import TestIntelligence
from syra.intelligence.optimizer import Optimizer

__all__ = ["TestIntelligence", "Optimizer"]
