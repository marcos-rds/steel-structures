"""Small pure proof specs shared by unit tests and the real FreeCAD fixture."""
from dataclasses import replace
from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures.assemblies import InterconnectorSpec, DistributionSpec
from freecad.SteelStructures.assemblies.presets import spaced_pair, double_channel, double_angle


def proof_specs():
    channel = profile_catalog.ref_for_designation('U 4" x 8,04')
    angle = profile_catalog.ref_for_designation('L 40 x 4')
    flat = profile_catalog.ref_for_designation('Barra Chata 50,8x6,35')
    pair = spaced_pair("PAIR", channel, 240.)
    def connected(base, kind):
        connector = InterconnectorSpec("WEB", kind, ("A", "B"),
            flat if kind == "Battens" else angle, start_offset=100., end_offset=150.,
            distribution=DistributionSpec(station_count=4))
        return replace(base, interconnectors=(connector,))
    channel_pair = double_channel("CHANNEL", channel, 240., "inward")
    return (pair, connected(pair, "Battens"), connected(pair, "SingleLacing"),
            connected(pair, "DoubleLacing"), connected(channel_pair, "Battens"),
            connected(channel_pair, "SingleLacing"),
            connected(double_angle("ANGLE", angle, 240.), "SingleLacing"))
