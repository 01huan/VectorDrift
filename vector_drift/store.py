from .shop import *
from .shop import Shop as Store
StoreScene = None
try:
    from .scenes.shop import ShopScene as StoreScene
except Exception:
    pass

