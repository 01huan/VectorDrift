import vector_drift.store as store_module
from vector_drift import shop


def test_store_reexports_shop():
    assert store_module.Shop is shop.Shop
    assert store_module.Store is shop.Shop
    assert store_module.purchase_item is shop.purchase_item
    assert store_module.all_items is shop.all_items


def test_store_scene_alias_is_none_or_scene():
    # In headless/no-pygame-import-of-scene path it may be None; either is acceptable.
    assert store_module.StoreScene is None or store_module.StoreScene.__name__ == "ShopScene"
