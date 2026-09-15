# Road Blockage detection

`ROAD_BLOCKAGE` is a human-reviewed proposal built on existing tracked-vehicle
motion. It is not an alias for `STOPPED_VEHICLE`.

Each camera may define zero or more `blockage_zones`. A zone contains a polygon,
traffic direction, minimum detection-box overlap, significant-overlap threshold,
and optional upstream traffic thresholds. With no configured zones, blockage
detection is disabled and existing behavior is unchanged.

The staged rule requires:

1. A tracked vehicle satisfies the existing stationary duration and speed state.
2. Its current detection box overlaps a configured active zone.
3. Detection-box/zone intersection measures image-space obstruction significance.
4. When direction geometry exists, slow vehicles upstream strengthen confidence.

One track produces one event per stationary episode. Movement or a safe detection
gap rearms the track. All outputs remain `PROPOSED` and use existing RBAC,
persistence, audit, and evidence APIs.

The obstruction ratio is intersection area divided by configured zone area. It is
an image-space diagnostic, not a physical percentage of a lane.

## Validation status

The rule and pipeline are synthetic/unit validated. The existing stopped-vehicle
clip shows a broken red car at the curb/road edge while traffic moves behind it;
it does not provide calibrated proof that an active lane is blocked. Therefore:

**REAL ROAD BLOCKAGE VIDEO REQUIRED**
