from dataclasses import dataclass


@dataclass(frozen=True)
class City:
    name: str
    state: str
    lat: float
    lon: float

    @property
    def slug(self) -> str:
        return f"{self.name.lower().replace(' ', '_')}_{self.state.lower()}"


TRISTATE_CITIES: list[City] = [
    # New York
    City("New York City", "NY", 40.7128, -74.0060),
    City("Buffalo", "NY", 42.8864, -78.8784),
    City("Rochester", "NY", 43.1566, -77.6088),
    City("Albany", "NY", 42.6526, -73.7562),
    City("Yonkers", "NY", 40.9312, -73.8988),
    City("Syracuse", "NY", 43.0481, -76.1474),
    City("White Plains", "NY", 41.0340, -73.7629),
    # New Jersey
    City("Newark", "NJ", 40.7357, -74.1724),
    City("Jersey City", "NJ", 40.7178, -74.0431),
    City("Paterson", "NJ", 40.9168, -74.1718),
    City("Elizabeth", "NJ", 40.6640, -74.2107),
    City("Trenton", "NJ", 40.2170, -74.7429),
    City("Edison", "NJ", 40.5187, -74.4121),
    # Connecticut
    City("Bridgeport", "CT", 41.1865, -73.1952),
    City("New Haven", "CT", 41.3083, -72.9279),
    City("Stamford", "CT", 41.0534, -73.5387),
    City("Hartford", "CT", 41.7658, -72.6851),
    City("Waterbury", "CT", 41.5582, -73.0515),
    City("Norwalk", "CT", 41.1177, -73.4082),
]
