import pandas as pd
import pvlib
from pvlib.pvsystem import PVSystem
from pvlib.modelchain import ModelChain
from pvlib.location import Location



def get_pv_feedin(filename='data/Lifuka_weather_2005.csv'):

    """ This function converts the FeedinWeather object built in Scrip_Merra2 into a feed-in-timeseries (PV_feedin)
    of a PV module with the help of PVLib's ModelChain, Location, PVSystem

    parameters:
    filename        as string (including the full path of the Merra2- FeedinWeather object)

    out/res:
    PV_feedin       as Pandas.Series [W/Wp]

    """
    weather=pd.read_csv(filename)
    weather.rename(columns={'v_wind': 'wind_speed'}, inplace=True)
    weather.set_index(pd.to_datetime(weather['timestamp']), inplace=True)

    times= weather.index

    # Initialize PV Module
    sandia_modules = pvlib.pvsystem.retrieve_sam('SandiaMod')
    sapm_inverters = pvlib.pvsystem.retrieve_sam('sandiainverter')

    # own module parameters
    invertername = 'ABB__MICRO_0_25_I_OUTD_US_240_240V__CEC_2014_'

    yingli230 = {
        'module_parameters': sandia_modules['Yingli_Solar_YL230_29b_Module__2009__E__'],
        'inverter_parameters': sapm_inverters[invertername],
        'surface_azimuth': 0,
        'surface_tilt': 25,
        'albedo': 0.2}

    location = {
        'latitude': -20,
        'longitude': -174.375,
        'tz': 'Pacific/Tongatapu',
        'altitude': 9.90,
        'name': 'Lifuka'}

    mc = ModelChain(PVSystem(**yingli230), Location(**location), orientation_strategy='south_at_latitude_tilt')
    mc.complete_irradiance(times=times, weather=weather)
    mc.run_model()
    nominal_module_capacity = 230

    res = pd.DataFrame()

    res['pv'] = mc.dc.p_mp.fillna(0)/nominal_module_capacity

    return res


