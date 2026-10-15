"""
Integration Test for Backtest Benchmarking (Task F)
"""
import pytest
from backtest.harness import BacktestSimulator


def test_optimizer_beats_all_three_baselines():
    """
    Test condition from spec:
    'Optimizer beats all three baselines on profit, or the loss is documented honestly'
    """
    sim = BacktestSimulator(seed=42)
    results = sim.run_simulation(num_periods=6, budget_per_period=3500.0)

    opt_profit = results["MarketPulse Optimizer"]["total_net_profit"]
    eq_profit = results["Equal Budget Split"]["total_net_profit"]
    ha_profit = results["Historical Average"]["total_net_profit"]
    ft_profit = results["Fixed-Threshold (s,S)"]["total_net_profit"]

    # MarketPulse must beat all 3 baselines
    assert opt_profit > eq_profit, f"Optimizer profit ${opt_profit} did not beat Equal Split ${eq_profit}"
    assert opt_profit > ha_profit, f"Optimizer profit ${opt_profit} did not beat Historical Avg ${ha_profit}"
    assert opt_profit > ft_profit, f"Optimizer profit ${opt_profit} did not beat Fixed-Threshold ${ft_profit}"

    # MarketPulse must have significantly less excess inventory waste
    opt_waste = results["MarketPulse Optimizer"]["excess_inventory_value"]
    ha_waste = results["Historical Average"]["excess_inventory_value"]
    assert opt_waste < ha_waste, f"Optimizer waste ${opt_waste} exceeded baseline waste ${ha_waste}"
