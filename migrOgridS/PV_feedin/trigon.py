"""
Irradiance on an inclined plane
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Using trigonometry (Lambert's cosine law, etc).
"""

import numpy as np
import pandas as pd


def _incidence_fixed(sun_alt, tilt, azimuth, sun_azimuth):
    return np.arccos(np.sin(sun_alt) * np.cos(tilt)
                     + np.cos(sun_alt) * np.sin(tilt)
                     * np.cos(azimuth - sun_azimuth))


def poa_irradiance(dirhi, dhi, dni, coords, sun_elevation, sun_azimuth, tilt=0, azimuth=180, albedo=0.3):
    """
    Args:
        direct : a series of direct horizontal irradiance with a datetime index
        diffuse : a series of diffuse horizontal irradiance with the same
                  datetime index as for direct
        coords : (lat, lon) tuple of location coordinates
        tilt : angle of panel relative to the horizontal plane, 0 = flat
        azimuth : deviation of the tilt direction from the meridian,
                  0 = towards pole, going clockwise, 3.14 = towards equator
        tracking : 0 (none, default), 1 (tilt), or 2 (tilt and azimuth).
                   If 1, azimuth is the orientation of the tilt axis, which
                   can be horizontal (tilt=0) or tilted.
        albedo : reflectance of the surrounding surface
        dni_only : only calculate and directly return a DNI time series
                   (ignores tilt, azimuth, tracking and albedo arguments)
        sun_elevation: elevation or altitude angle in degrees
        sun_azimuth: azimuth_angle of the sun
    """
    # 0. Correct azimuth if we're on southern hemisphere, so that 3.14
    # points north instead of south
    if coords[0] < 0:
        azimuth = azimuth + np.pi

    incidence = _incidence_fixed(sun_elevation, tilt, azimuth,sun_azimuth)
    panel_tilt = tilt

    plane_direct = (dni * np.cos(incidence)).fillna(0).clip_lower(0)
    plane_diffuse = (dhi * ((1 + np.cos(panel_tilt)) / 2)
                     + albedo * (dirhi + dhi)
                     * ((1 - np.cos(panel_tilt)) / 2)).fillna(0)
    return pd.DataFrame({'direct': plane_direct, 'diffuse': plane_diffuse})

