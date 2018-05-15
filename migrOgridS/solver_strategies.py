import pandas as pd
from oemof.outputlib import views,processing
import cost_summary as lcoe
import main


def rolling_horizon(PV, Storage, SH=8760,PH=120, CH=120,):
    iter = 0
    start = 0
    stop = PH
    mode = 'simulation'
    initial_capacity=0.5

    path = 'results'
    filepath = '/diesel_pv_batt_PH120_P1_B1'

    components_list = ['demand', 'PV', 'storage', 'pp_oil_1', 'pp_oil_2', 'pp_oil_3', 'excess']

    results_list = []
    economic_list = []

    cost = main.get_cost_dict( PH )
    file = 'data/timeseries.csv'

    timeseries = pd.read_csv( file, sep=';' )
    timeseries.set_index( pd.DatetimeIndex( timeseries['timestamp'], freq='H' ), inplace=True )
    timeseries.drop( labels='timestamp', axis=1, inplace=True )
    timeseries[timeseries['PV'] > 1] = 1

    itermax = int( (SH / CH) - 1 )
    objective=0.0

    while iter <= itermax:

        if iter == 0:
            status = True
        else:
            status = False

        feedin_RH = timeseries.iloc[start:stop]

        print( str( iter + 1 ) + '/' + str( itermax + 1 ) )

        m = main.create_optimization_model( mode, feedin_RH, initial_capacity,cost,PV, Storage,  iterstatus=status)[0]

        results_el = main.solve_and_create_results( m )
        objective+=processing.meta_results(m)['objective']

        initial_capacity = views.node( results_el, 'storage' )['sequences'][(('storage', 'None'), 'capacity')][CH - 1]

        start += CH
        stop += CH

        iter += 1


    return objective

if __name__ == '__main__':
    PV=250
    Storage=273

    print(rolling_horizon(PV,Storage))
