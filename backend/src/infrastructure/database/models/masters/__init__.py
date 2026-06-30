"""Master data ORM models."""

from src.infrastructure.database.models.masters.product_type_model import ProductTypeMasterModel  # noqa: F401
from src.infrastructure.database.models.masters.pack_size_model import PackStyleMasterModel  # noqa: F401
from src.infrastructure.database.models.masters.type_of_pallet_model import TypeOfPalletMasterModel  # noqa: F401
from src.infrastructure.database.models.masters.country_model import CountryMasterModel  # noqa: F401
from src.infrastructure.database.models.masters.city_model import CityMasterModel  # noqa: F401
from src.infrastructure.database.models.masters.air_master_model import AirMasterModel, AirMasterRateModel  # noqa: F401
from src.infrastructure.database.models.masters.sea_master_model import SeaMasterModel, SeaMasterRateModel  # noqa: F401
from src.infrastructure.database.models.masters.sea_cbm_master_model import SeaCbmMasterModel  # noqa: F401
from src.infrastructure.database.models.masters.vehicle_type_master_model import VehicleTypeMasterModel  # noqa: F401
from src.infrastructure.database.models.masters.local_master_model import LocalMasterModel, LocalMasterRateModel  # noqa: F401
