"""Data models for the RAG pipeline."""
from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class Annotation:
    name: str
    params: str = ""


@dataclass
class Field:
    name: str
    type_name: str
    annotations: List[Annotation] = field(default_factory=list)


@dataclass
class Method:
    name: str
    return_type: str = ""
    parameters: str = ""
    annotations: List[Annotation] = field(default_factory=list)
    javadoc: str = ""
    line: int = 0


@dataclass
class SettingsRef:
    """A reference to a configuration setting from code."""
    setting_key: str
    default_value: str = ""
    source_annotation: str = ""     # @Value, property constant, etc.
    field_name: str = ""
    context: str = ""               # method/class where it's used
    file_path: str = ""


@dataclass
class BranchingLogic:
    """A conditional branch driven by a setting."""
    field_name: str
    setting_key: str
    method_name: str
    condition_type: str = ""        # "if", "switch", "ternary"
    condition_text: str = ""
    file_path: str = ""
    line: int = 0


@dataclass
class ParsedClass:
    name: str
    class_type: str                 # 'class', 'interface', 'enum', 'abstract_class', 'annotation'
    package: str
    file_path: str
    module: str

    extends: str = ""
    implements: List[str] = field(default_factory=list)
    annotations: List[Annotation] = field(default_factory=list)
    fields: List[Field] = field(default_factory=list)
    methods: List[Method] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    inner_classes: List[str] = field(default_factory=list)

    settings_refs: List[SettingsRef] = field(default_factory=list)
    branching_logic: List[BranchingLogic] = field(default_factory=list)

    javadoc: str = ""
    spring_stereotype: str = ""     # @Controller, @Service, @Repository, @Component, @Configuration
    request_mappings: List[str] = field(default_factory=list)
    is_public: bool = True
    line_count: int = 0

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)


@dataclass
class ParsedMapper:
    file_path: str
    module: str
    namespace: str = ""
    statements: List[Dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)


@dataclass
class ParsedProperties:
    file_path: str
    module: str
    profile: str = ""               # development, production, etc.
    properties: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)


@dataclass
class Domain:
    name: str
    module: str
    channel: str = ""               # empty = cross-cutting
    packages: List[str] = field(default_factory=list)
    class_names: List[str] = field(default_factory=list)
    class_count: int = 0
    mapper_count: int = 0
    description: str = ""           # filled by LLM
    settings_map: Dict[str, List[dict]] = field(default_factory=dict)
    branching_points: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)


# Channel detection patterns: package/path fragment → channel name
CHANNEL_PATTERNS = {
    # Order matters: more specific patterns first
    # NOTE: "mybookingpal" is the company name, NOT a channel
    # Channels are detected from sub-packages like .bookingcom., .airbnb., etc.
    "event.bookingcom": "bookingcom",
    "rest.bookingcom": "bookingcom",
    ".bookingcom": "bookingcom",
    ".airbnb": "airbnb",
    ".expedia": "expedia",
    ".homeaway": "homeaway_vrbo",
    ".vrbo": "homeaway_vrbo",
    ".agoda": "agoda",
    ".ctrip": "ctrip",
    ".tripadvisor": "tripadvisor",
    ".fewo": "fewo",
    ".inntopia": "inntopia",
    ".marriott": "marriott",
    ".googlehotelads": "google_hotel_ads",
    ".getaroom": "getaroom",
    ".flats9": "flats9",
    ".thirdhome": "thirdhome",
    ".razor": "razor",
    ".wyndham": "wyndham",
    ".hyatt": "hyatt",
    ".escapia": "escapia",
    ".siteminder": "siteminder",
    ".maxxton": "maxxton",
    ".ciirus": "ciirus",
    ".nextpax": "nextpax",
    ".barefoot": "barefoot",
    ".interhome": "interhome",
    ".maestro": "maestro",
    ".guesty": "guesty",
    ".liverez": "liverez",
    ".streamline": "streamline",
    ".kigo": "kigo",
    ".lodgify": "lodgify",
    ".homerez": "homerez",
    ".vacasa": "vacasa",
    ".synxis": "synxis",
    ".channeladvisor": "channeladvisor",
}

