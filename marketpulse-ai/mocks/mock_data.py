"""
Mock Data Generator for Member 1 (Catalog) & Member 2 (Forecasts)

Provides a realistic small grocery/retail basket of 15 products scaled
for a monthly replenishment budget of $3,000 to $7,000.
"""
from typing import Dict, Tuple
from optimizer.models import Forecast, InventoryState, ProductMeta


def get_mock_retail_store() -> Tuple[Dict[str, Forecast], Dict[str, InventoryState], Dict[str, ProductMeta]]:
    """
    Returns (forecasts, inventory, products) for 15 representative retail SKUs.
    Total unconstrained reorder cost is ~$6,500, making $5,000 and $3,000
    realistic budget-binding thresholds for the hackathon demo.
    """
    products: Dict[str, ProductMeta] = {
        "SKU_MILK_1L": ProductMeta(
            product_id="SKU_MILK_1L",
            name="Whole Milk 1L",
            category="Dairy",
            purchase_price=1.20,
            selling_price=1.80,
            holding_cost=0.08,
            salvage_value=0.20,
            lead_time_days=1,
            min_order_qty=24,
            pack_size=12,
            unit_volume=1.0,
            shelf_life_days=12
        ),
        "SKU_BREAD_WHITE": ProductMeta(
            product_id="SKU_BREAD_WHITE",
            name="Sliced White Bread",
            category="Bakery",
            purchase_price=0.90,
            selling_price=1.50,
            holding_cost=0.10,
            salvage_value=0.10,
            lead_time_days=1,
            min_order_qty=30,
            pack_size=10,
            unit_volume=1.2,
            shelf_life_days=6
        ),
        "SKU_EGGS_DOZEN": ProductMeta(
            product_id="SKU_EGGS_DOZEN",
            name="Eggs 12-pack",
            category="Dairy",
            purchase_price=2.20,
            selling_price=3.40,
            holding_cost=0.15,
            salvage_value=0.40,
            lead_time_days=2,
            min_order_qty=20,
            pack_size=10,
            unit_volume=1.5,
            shelf_life_days=21
        ),
        "SKU_RICE_5KG": ProductMeta(
            product_id="SKU_RICE_5KG",
            name="Long Grain Rice 5kg",
            category="Staples",
            purchase_price=6.50,
            selling_price=9.50,
            holding_cost=0.15,
            salvage_value=3.00,
            lead_time_days=3,
            min_order_qty=10,
            pack_size=5,
            unit_volume=5.0,
            shelf_life_days=365
        ),
        "SKU_COOKING_OIL_2L": ProductMeta(
            product_id="SKU_COOKING_OIL_2L",
            name="Vegetable Cooking Oil 2L",
            category="Staples",
            purchase_price=4.80,
            selling_price=7.20,
            holding_cost=0.15,
            salvage_value=2.00,
            lead_time_days=3,
            min_order_qty=12,
            pack_size=6,
            unit_volume=2.2,
            shelf_life_days=365
        ),
        "SKU_SUGAR_2KG": ProductMeta(
            product_id="SKU_SUGAR_2KG",
            name="White Sugar 2kg",
            category="Staples",
            purchase_price=2.10,
            selling_price=3.20,
            holding_cost=0.08,
            salvage_value=1.00,
            lead_time_days=2,
            min_order_qty=20,
            pack_size=10,
            unit_volume=2.0,
            shelf_life_days=365
        ),
        "SKU_FLOUR_5KG": ProductMeta(
            product_id="SKU_FLOUR_5KG",
            name="All-Purpose Flour 5kg",
            category="Staples",
            purchase_price=4.20,
            selling_price=6.00,
            holding_cost=0.12,
            salvage_value=2.00,
            lead_time_days=3,
            min_order_qty=10,
            pack_size=5,
            unit_volume=4.5,
            shelf_life_days=180
        ),
        "SKU_INSTANT_COFFEE": ProductMeta(
            product_id="SKU_INSTANT_COFFEE",
            name="Instant Coffee Jar 200g",
            category="Beverages",
            purchase_price=7.50,
            selling_price=11.50,
            holding_cost=0.25,
            salvage_value=3.50,
            lead_time_days=4,
            min_order_qty=12,
            pack_size=6,
            unit_volume=1.0,
            shelf_life_days=365
        ),
        "SKU_BLACK_TEA_BOX": ProductMeta(
            product_id="SKU_BLACK_TEA_BOX",
            name="Black Tea Bags 100s",
            category="Beverages",
            purchase_price=2.80,
            selling_price=4.40,
            holding_cost=0.08,
            salvage_value=1.20,
            lead_time_days=2,
            min_order_qty=15,
            pack_size=15,
            unit_volume=0.8,
            shelf_life_days=365
        ),
        "SKU_SODA_CASE_24": ProductMeta(
            product_id="SKU_SODA_CASE_24",
            name="Cola Soda Case (24 cans)",
            category="Beverages",
            purchase_price=9.50,
            selling_price=16.00,
            holding_cost=0.30,
            salvage_value=4.00,
            lead_time_days=2,
            min_order_qty=10,
            pack_size=5,
            unit_volume=8.0,
            shelf_life_days=180
        ),
        "SKU_POTATO_CHIPS_BOX": ProductMeta(
            product_id="SKU_POTATO_CHIPS_BOX",
            name="Potato Chips Box (20 bags)",
            category="Snacks",
            purchase_price=10.00,
            selling_price=18.00,
            holding_cost=0.35,
            salvage_value=4.00,
            lead_time_days=2,
            min_order_qty=8,
            pack_size=4,
            unit_volume=6.0,
            shelf_life_days=90
        ),
        "SKU_CHOCOLATE_BOX": ProductMeta(
            product_id="SKU_CHOCOLATE_BOX",
            name="Chocolate Bars Box (30 bars)",
            category="Snacks",
            purchase_price=18.00,
            selling_price=30.00,
            holding_cost=0.60,
            salvage_value=8.00,
            lead_time_days=3,
            min_order_qty=5,
            pack_size=5,
            unit_volume=3.0,
            shelf_life_days=180
        ),
        "SKU_LAUNDRY_DETERGENT": ProductMeta(
            product_id="SKU_LAUNDRY_DETERGENT",
            name="Laundry Detergent Powder 3kg",
            category="Household",
            purchase_price=5.50,
            selling_price=8.50,
            holding_cost=0.15,
            salvage_value=2.50,
            lead_time_days=3,
            min_order_qty=12,
            pack_size=6,
            unit_volume=3.5,
            shelf_life_days=730
        ),
        "SKU_BATH_SOAP_PACK": ProductMeta(
            product_id="SKU_BATH_SOAP_PACK",
            name="Bath Soap Bar (Pack of 6)",
            category="Personal Care",
            purchase_price=3.50,
            selling_price=5.60,
            holding_cost=0.10,
            salvage_value=1.50,
            lead_time_days=2,
            min_order_qty=16,
            pack_size=8,
            unit_volume=1.8,
            shelf_life_days=730
        ),
        # Specialty high-risk item: high unit cost $45, low sales frequency, extreme variance
        "SKU_EXOTIC_SPICE_CASE": ProductMeta(
            product_id="SKU_EXOTIC_SPICE_CASE",
            name="Imported Gourmet Saffron Case",
            category="Specialty",
            purchase_price=45.00,
            selling_price=68.00,
            holding_cost=3.00,
            salvage_value=10.00,
            lead_time_days=7,
            min_order_qty=4,
            pack_size=2,
            unit_volume=1.0,
            shelf_life_days=365
        )
    }

    # Forecasts for 30-day monthly planning cycle
    forecasts: Dict[str, Forecast] = {
        "SKU_MILK_1L": Forecast(p10=320, p50=420, p90=540, horizon_days=30),
        "SKU_BREAD_WHITE": Forecast(p10=280, p50=380, p90=490, horizon_days=30),
        "SKU_EGGS_DOZEN": Forecast(p10=140, p50=200, p90=270, horizon_days=30),
        "SKU_RICE_5KG": Forecast(p10=80, p50=120, p90=165, horizon_days=30),
        "SKU_COOKING_OIL_2L": Forecast(p10=70, p50=105, p90=145, horizon_days=30),
        "SKU_SUGAR_2KG": Forecast(p10=100, p50=150, p90=205, horizon_days=30),
        "SKU_FLOUR_5KG": Forecast(p10=60, p50=90, p90=125, horizon_days=30),
        "SKU_INSTANT_COFFEE": Forecast(p10=30, p50=55, p90=85, horizon_days=30),
        "SKU_BLACK_TEA_BOX": Forecast(p10=60, p50=90, p90=125, horizon_days=30),
        "SKU_SODA_CASE_24": Forecast(p10=45, p50=75, p90=110, horizon_days=30),
        "SKU_POTATO_CHIPS_BOX": Forecast(p10=35, p50=60, p90=90, horizon_days=30),
        "SKU_CHOCOLATE_BOX": Forecast(p10=20, p50=38, p90=60, horizon_days=30),
        "SKU_LAUNDRY_DETERGENT": Forecast(p10=40, p50=65, p90=95, horizon_days=30),
        "SKU_BATH_SOAP_PACK": Forecast(p10=50, p50=80, p90=115, horizon_days=30),
        # Extreme uncertainty: (120 - 4) / 25 = 4.64 > 1.25!
        "SKU_EXOTIC_SPICE_CASE": Forecast(p10=4, p50=25, p90=120, horizon_days=30)
    }

    # Starting inventory positions (roughly 5-7 days of stock)
    inventory: Dict[str, InventoryState] = {
        "SKU_MILK_1L": InventoryState(on_hand=60, on_order=0, expired_stock=6, days_to_next_replenishment=30),
        "SKU_BREAD_WHITE": InventoryState(on_hand=40, on_order=0, expired_stock=0, days_to_next_replenishment=30),
        "SKU_EGGS_DOZEN": InventoryState(on_hand=30, on_order=0, expired_stock=0, days_to_next_replenishment=30),
        "SKU_RICE_5KG": InventoryState(on_hand=20, on_order=10, expired_stock=0, days_to_next_replenishment=30),
        "SKU_COOKING_OIL_2L": InventoryState(on_hand=15, on_order=0, expired_stock=0, days_to_next_replenishment=30),
        "SKU_SUGAR_2KG": InventoryState(on_hand=25, on_order=0, expired_stock=0, days_to_next_replenishment=30),
        "SKU_FLOUR_5KG": InventoryState(on_hand=15, on_order=0, expired_stock=0, days_to_next_replenishment=30),
        "SKU_INSTANT_COFFEE": InventoryState(on_hand=10, on_order=0, expired_stock=0, days_to_next_replenishment=30),
        "SKU_BLACK_TEA_BOX": InventoryState(on_hand=20, on_order=0, expired_stock=0, days_to_next_replenishment=30),
        "SKU_SODA_CASE_24": InventoryState(on_hand=12, on_order=0, expired_stock=0, days_to_next_replenishment=30),
        "SKU_POTATO_CHIPS_BOX": InventoryState(on_hand=10, on_order=0, expired_stock=0, days_to_next_replenishment=30),
        "SKU_CHOCOLATE_BOX": InventoryState(on_hand=8, on_order=0, expired_stock=0, days_to_next_replenishment=30),
        "SKU_LAUNDRY_DETERGENT": InventoryState(on_hand=12, on_order=0, expired_stock=0, days_to_next_replenishment=30),
        "SKU_BATH_SOAP_PACK": InventoryState(on_hand=16, on_order=0, expired_stock=0, days_to_next_replenishment=30),
        "SKU_EXOTIC_SPICE_CASE": InventoryState(on_hand=3, on_order=0, expired_stock=0, days_to_next_replenishment=30)
    }

    return forecasts, inventory, products
