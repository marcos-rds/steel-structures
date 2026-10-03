"""Station identities use reduced rational positions within semantic branches."""
from fractions import Fraction
from .models import Station, StationPlan
from .envelope import validate_envelope


def allocate_panels(count, apex_position):
    if type(count) is not int or count < 4:
        raise ValueError("C1 exige pelo menos 4 painéis inteiros.")
    left = max(1, min(count - 1, int(count * apex_position + 0.5)))
    return left, count - left


def _fraction_key(branch, index, count):
    value = Fraction(index, count)
    return "S_{}_{}_{}".format(branch, value.numerator, value.denominator)


def panelize(definition, count, allocation=None):
    validate_envelope(definition)
    allocate_panels(count, definition.apex_position)
    if definition.kind == "Parallel":
        stations = [Station("S_START", 0., True)]
        stations.extend(Station(_fraction_key("MAIN", i, count), definition.span*i/count)
                        for i in range(1, count))
        stations.append(Station("S_END", definition.span, True))
        return StationPlan(tuple(stations), count)
    left, right = allocation or allocate_panels(count, definition.apex_position)
    if (isinstance(left, bool) or isinstance(right, bool) or int(left) != left
            or int(right) != right or left < 1 or right < 1 or left+right != count):
        raise ValueError("Distribuição de painéis nas águas inválida.")
    apex = definition.span * definition.apex_position
    stations = [Station("S_START", 0., True, "LEFT")]
    stations.extend(Station(_fraction_key("LEFT", i, left), apex*i/left, False, "LEFT")
                    for i in range(1, left))
    stations.append(Station("S_APEX", apex, True, "APEX"))
    stations.extend(Station(_fraction_key("RIGHT", i, right), apex+(definition.span-apex)*i/right,
                            False, "RIGHT") for i in range(1, right))
    stations.append(Station("S_END", definition.span, True, "RIGHT"))
    return StationPlan(tuple(stations), count, left, right)
