import pandas as pd
import numpy as np
from pvlib import solarposition as sp
from collections import OrderedDict
from pvlib import tools
from pvlib import irradiance
from pvlib.location import Location
from reninjas_pv import run_plant_model


LAT_STEP = 0.5
LON_STEP = 0.625


def slice_merra2(points, csv_merra2=None):
    """ This script can be used to read hourly Merra2-Data (.csv) and to convert this weather data set to a weather
    set that can be read by FeedInLib

    parameters:
    lat = latitude of location as float e.g. 4.0
    lon = longitude of location as float e.g. 116.25
    csv_merra2=['STRINGNAME.csv'] as string , STRINGNAME= path to downloaded Dataframe from Merra2 via
    https://data.open-power-system-data.org/weather_data/

    out:
    weather merra as DataFrame that can be used as feedinlib.FeedinWeather[data]
    """
    # Initialise weather dataframe
    if not isinstance(points, list):
        points = [points]
    weather_merra = [pd.DataFrame() for i in range(len(points))]

    # Adapt points longitude and latitude to discrete values:
    discrete_points = []
    for point in points:
        lat_discrete = round(round(point[0] / LAT_STEP) * LAT_STEP, 3)
        lon_discrete = round(round(point[1] / LON_STEP) * LON_STEP, 3)
        discrete_points.append((lat_discrete, lon_discrete))

    text_file_reader = pd.read_csv(csv_merra2, chunksize=10000)  # Read Merra2-csv chunkwise (big size)

    for c, chunk in enumerate(text_file_reader):  # Loop over chunks
        print(str(c) + '/551')
        for i, dis_point in enumerate(discrete_points):
            stacked = chunk[round(chunk.lat, 3) == dis_point[0]][round(chunk.lon, 3) == dis_point[1]]  # Select rows of chunk that refer to location (lat, lon)
            weather_merra[i] = pd.concat([weather_merra[i], stacked])  # Save selected rows of chunk in weather_merra DataFrame

    # Clean data:
    for weather in weather_merra:
        weather.set_index('timestamp', inplace=True)
        weather['T'] = weather['T'] - 273.15 # change Kelvin to degrees celcius
        weather.rename(
            columns={'SWGDN': 'ghi', 'SWTDN': 'TOA_i', 'p': 'pressure', 'T': 'temp_air', 'v_50m': 'v_wind'}
            , inplace=True)
        # weather.drop(['cumulated hours', 'lat', 'lon'], axis=1, inplace=True)

    return weather_merra


def get_sunpos (weather, lat, lon):
    if hasattr(weather, 'pressure'):
        p = np.average(weather['pressure'])
    else:
        p = None
    if hasattr(weather, 'temp_air'):
        t = np.average(weather['temp_air'])
    else:
        t = None

    sun_pos = sp.get_solarposition(weather.index, lat, lon, altitude=9.90, pressure=p, temperature=t)
    return sun_pos


def doy (weather):
    times = pd.DatetimeIndex(weather.index)
    doy = times.dayofyear
    return doy


def reindl (lat,lon, times, ghi, extra_i, zenith):
    """
    this function calculates dhi, dni and the clearness index kt
    from ghi, extraterrestial_irradiance and the solar zenith propsed by Merra2
    [1]

    Parameters
    -----------
        ghi:  numeric pd.Series or sequence
        global horizontal irradiance [W/m^2]

        zenith: numeric pd.Series or sequence
        real solar zenith angle (not apparent) in [°]

        extra_i: numeric pd.Series or sequence
        extraterrestial irradiance [W/m^2] == top-of-the-atmosphere irradiance (TOA) == SWTDN (Merra-2)

    Returns
    -------
    data : OrderedDict or DataFrame
        Contains the following keys/columns:

            * ``dni``: the modeled direct normal irradiance in W/m^2.
            * ``dhi``: the modeled diffuse horizontal irradiance in
              W/m^2.
            * ``kt``: Ratio of global to extraterrestrial irradiance
              on a horizontal plane.

    References
    -----------
        [1] Reindl et al. (1990): Diffuse fraction correlations

    """

    i0_h = extra_i * tools.cosd(zenith)

    kt = ghi / i0_h

    kt = np.maximum(kt, 0)
    kt.fillna(0, inplace=True)

    # for kt outside the boundaries, set diffuse fraction to zero
    df = 0.0

    # for 0<kt<=0.3  set diffuse fraction
    df = np.where((kt > 0) & (kt <= 0.3), 1.02 - 0.254 * kt + 0.0123 * tools.cosd(zenith), df)

    # for 0.3<kt<0.78  and df>=0.1, set diffuse fraction
    df = np.where((kt > 0.3) & (kt <= 0.78) & (1.4 - 1.794 * kt + 0.177 * tools.cosd(zenith) >= 0.1),
                  1.4 - 1.794 * kt + 0.177 * tools.cosd(zenith), df)
    # for kt > 0.78 and df>=0.1
    df = np.where((kt > 0.78) & (0.486 * kt + 0.182 * tools.cosd(zenith) >= 0.1),
                  0.486 * kt + 0.182 * tools.cosd(zenith), df)

    # remove extreme values
    df = np.where((df < 0.9) & (kt < 0.2), 0, df)
    df = np.where((df > 0.8) & (kt > 0.6), 0, df)
    df = np.where((df > 1), 0, df)
    df = np.where(((ghi - extra_i) >= 0), 0, df)

    dhi = df * ghi

    dni = irradiance.dni(ghi, dhi, zenith,
                         clearsky_dni=Location(lat, lon).get_clearsky(times).dni,
                         zenith_threshold_for_zero_dni=88.0,
                         clearsky_tolerance=1.1,
                         zenith_threshold_for_clearsky_limit=64)

    data = OrderedDict()
    data['dni'] = dni
    data['dhi'] = dhi
    data['kt'] = kt

    if isinstance(dni, pd.Series):
        data = pd.DataFrame(data)

    return data


def erbs (ghi,extra_i, zenith):
    r"""
    Estimate DNI and DHI from GHI using the Erbs model.

    The Erbs model [1]_ estimates the diffuse fraction DF from global
    horizontal irradiance through an empirical relationship between DF
    and the ratio of GHI to extraterrestrial irradiance, Kt. The
    function uses the diffuse fraction to compute DHI as

    .. math::

        DHI = DF \times GHI

    DNI is then estimated as

    .. math::

        DNI = (GHI - DHI)/\cos(Z)

    where Z is the zenith angle. Unreasonable values of

    Parameters
    ----------
    ghi: numeric
        Global horizontal irradiance in W/m^2.
    zenith: numeric
        True (not refraction-corrected) zenith angles in decimal degrees.
    doy: scalar, array or DatetimeIndex
        The day of the year.

    Returns
    -------
    data : OrderedDict or DataFrame
        Contains the following keys/columns:

            * ``dni``: the modeled direct normal irradiance in W/m^2.
            * ``dhi``: the modeled diffuse horizontal irradiance in
              W/m^2.
            * ``kt``: Ratio of global to extraterrestrial irradiance
              on a horizontal plane.

    References
    ----------
    .. [1] D. G. Erbs, S. A. Klein and J. A. Duffie, Estimation of the
       diffuse radiation fraction for hourly, daily and monthly-average
       global radiation, Solar Energy 28(4), pp 293-302, 1982. Eq. 1

    """

    # This Z needs to be the true Zenith angle, not apparent,
    # to get extraterrestrial horizontal radiation)
    i0_h = extra_i * tools.cosd(zenith)

    kt = ghi / i0_h
    kt = np.maximum(kt, 0)

    # For Kt <= 0.22, set the diffuse fraction
    df = 1 - 0.09 * kt

    # For Kt > 0.22 and Kt <= 0.8, set the diffuse fraction
    df = np.where((kt > 0.22) & (kt <= 0.8),
                  0.9511 - 0.1604 * kt + 4.388 * kt ** 2 -
                  16.638 * kt ** 3 + 12.336 * kt ** 4,
                  df)

    # For Kt > 0.8, set the diffuse fraction
    df = np.where(kt > 0.8, 0.165, df)

    dhi = df * ghi

    dni = (ghi - dhi) / tools.cosd(zenith)

    data = OrderedDict()
    data['dni'] = dni
    data['dhi'] = dhi
    data['kt'] = kt

    if isinstance(dni, pd.Series):
        data = pd.DataFrame(data)

    return data


def philippines_pv(location_filepath=None):

    location = pd.read_csv(location_filepath, sep=',')
    location.set_index('Index', inplace=True)
    location.rename(columns={'Coor Lat': 'lat', 'Coor Long': 'lon'}, inplace=True)

    c=pd.DataFrame(data={'lat': [-20] ,'lon' : [-174.35]})
    df = pd.DataFrame(index=c.index)

    for i in c.itertuples():
        weather = slice_merra2(-20, -174.375, csv_merra2='data/weather_data_Tonga_2005.csv')

        ghi = weather['ghi']

        TOA_i = weather['TOA_i']

        times=pd.DatetimeIndex(weather.index)

        sun_pos = get_sunpos(weather, i[1], i[2])

        sun_zenith=sun_pos['zenith']

        sun_elevation=sun_pos['elevation']

        sun_azimuth=sun_pos['azimuth']

        data = reindl(i[1],i[2],times, ghi, TOA_i,sun_zenith)

        pv=run_plant_model(ghi/1000, data['dhi']/1000, data['dni']/1000, (i[1], [i[2]]),
                           tamb=weather['temp_air'],
                           sun_elevation=sun_elevation,
                           sun_azimuth=sun_azimuth)
    return pv
    #@Hendrik: Der for-loop ist noch nicht fertig!eigentlich soll hier der pv feedin für jeden standort in einem
    # pd.DataFrame(index=Index,columns=range(0,8760),data=pv) zurückgegeben werden


if __name__ == '__main__':
    # philippines_pv(location_filepath='data/philippines_coords.csv')

    merra2_file = 'data/weather_data_Tonga_2005.csv'
    merra2_file = 'data/weather_data_Paul_2014.csv'

    points = [(6.234, 121.546), (21.345436, 118.3425), (4.1, 120.5235)]
    weather = slice_merra2(points, csv_merra2=merra2_file)
    print(weather)
