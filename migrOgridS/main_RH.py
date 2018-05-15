import logging
import custom_constraints as constraints
import pandas as pd
import os
import time

from oemof.outputlib import processing, views
from oemof.solph import (Sink, Transformer, Source, Bus, Flow, NonConvex,
                         Model, EnergySystem, components, custom, Investment)
from oemof.tools import logger, economics
from oemof.network import Node
import cost_summary as lcoe

# cost dictionary #####################################################################################################
#######################################################################################################################

def get_cost_dict(PH):
    cost = {'pp_oil_1': {'fix': economics.annuity( (500 / 8760) * PH, 20, 0.094 ),
                         'var': 1.2,
                         'o&m': 0.02},
            'pp_oil_2': {'fix': economics.annuity( (500 / 8760) * PH, 20, 0.094 ),
                         'var': 1.2,
                         'o&m': 0.02},
            'pp_oil_3': {'fix': economics.annuity( (500 / 8760) * PH, 20, 0.094 ),
                         'var': 1.2,
                         'o&m': 0.02},
            'storage': {'fix': (3.88 / 8760) * PH,
                        'var': 0.087,
                        'epc': economics.annuity( (300 / 8760) * PH, 10, 0.094 )},
            'pv': {'fix': (25 / 8760) * PH,
                   'var': 0,
                   'epc': economics.annuity( (2500 / 8760) * PH, 20, 0.094 )}
            }
    return cost


def get_sim_params(cost):
    sim_params = {'pv': {'nominal_capacity': 265.017017,
                         'investment': Investment( ep_costs=cost['pv']['epc'] )},
                  'storage': {'nominal_capacity': 268.1211092,
                              'investment': Investment( ep_costs=cost['storage']['epc'] )}}
    return sim_params


def add_inverter(i, o, name, eta=1):
    return Transformer( label=name,
                        inputs={i: Flow()},
                        outputs={o: Flow()},
                        conversion_factors={o: eta} )


def create_optimization_model(mode, feedin, initial_batt_cap, cost, cap_pv, cap_batt,iterstatus=None, PV_source=True, storage_source=True,logger=False):

    if logger==1:
        logger.define_logging()

    ##################################### Initialize the energy system##################################################

    # times = pd.DatetimeIndex(start='04/01/2017', periods=10, freq='H')
    times = feedin.index

    energysystem = EnergySystem( timeindex=times )

    # switch on automatic registration of entities of EnergySystem-object=energysystem

    Node.registry = energysystem

    # add components

    b_el = Bus( label='electricity' )
    b_dc = Bus( label='electricity_dc' )
    b_oil = Bus( label='diesel_source' )

    demand_feedin = feedin['demand_el']

    Sink( label='demand',
          inputs={b_el: Flow( actual_value=demand_feedin,
                              nominal_value=1,
                              fixed=True )} )

    Sink( label='excess',
          inputs={b_el: Flow()} )


    Source( label='diesel',
            outputs={b_oil: Flow()} )

    generator1 = custom.DieselGenerator( label='pp_oil_1',
                                         fuel_input={b_oil: Flow( variable_costs=cost['pp_oil_1']['var'] )},
                                         electrical_output={b_el: Flow( nominal_value=186,
                                                                        min=0.3,
                                                                        max=1,
                                                                        nonconvex=NonConvex(
                                                                            om_costs=cost['pp_oil_1']['o&m'] ),
                                                                        fixed_costs=cost['pp_oil_1']['fix']
                                                                        )},
                                         fuel_curve={'1': 42, '0.75': 33, '0.5': 22, '0.25': 16} )

    generator2 = custom.DieselGenerator( label='pp_oil_2',
                                         fuel_input={b_oil: Flow( variable_costs=cost['pp_oil_2']['var'] )},
                                         electrical_output={b_el: Flow( nominal_value=186,
                                                                        min=0.3,
                                                                        max=1,
                                                                        nonconvex=NonConvex(
                                                                            om_costs=cost['pp_oil_2']['o&m'] ),
                                                                        fixed_costs=cost['pp_oil_2']['fix'],
                                                                        variable_costs=0 )},
                                         fuel_curve={'1': 42, '0.75': 33, '0.5': 22, '0.25': 16} )

    generator3 = custom.DieselGenerator( label='pp_oil_3',
                                         fuel_input={b_oil: Flow( variable_costs=cost['pp_oil_3']['var'] )},
                                         electrical_output={b_el: Flow( nominal_value=320,
                                                                        min=0.3,
                                                                        max=1,
                                                                        nonconvex=NonConvex(
                                                                            om_costs=cost['pp_oil_3']['o&m'] ),
                                                                        fixed_costs=cost['pp_oil_3']['fix'],
                                                                        variable_costs=0 )},
                                         fuel_curve={'1': 73, '0.75': 57, '0.5': 38, '0.25': 27} )

    # List all generators in a list called gen_set
    gen_set = [generator1, generator2, generator3]

    if PV_source == 1:
        PV = Source( label='PV',
                     outputs={b_dc: Flow( nominal_value=cap_pv,
                                          fixed_costs=cost['pv']['fix']+cost['pv']['epc'],
                                          actual_value=feedin['PV'],
                                          fixed=True)} )
    else:
        PV=None

    if storage_source == 1:
        storage = components.GenericStorage( label='storage',
                                             inputs={b_dc: Flow()},
                                             outputs={b_dc: Flow( variable_costs=cost['storage']['var'],
                                                                  fixed_costs=cost['storage']['fix'])},
                                             nominal_capacity=cap_batt,
                                             fixed_costs=cost['storage']['epc'],
                                             capacity_loss=0.00,
                                             initial_capacity=initial_batt_cap,
                                             nominal_input_capacity_ratio=0.546,
                                             nominal_output_capacity_ratio=0.546,
                                             inflow_conversion_factor=0.92,
                                             outflow_conversion_factor=0.92,
                                             capacity_min=0.5,
                                             capacity_max=1,
                                             initial_iteration=iterstatus )
    else:
        storage=None

    if storage_source == 1 or PV_source == 1:
        inverter1 = add_inverter( b_dc, b_el, 'Inv_pv' )

    ################################# optimization ############################
    # create Optimization model based on energy_system
    logging.info( "Create optimization problem" )

    m = Model( energysystem )

    ################################# constraints ############################

    sr_requirement = 0.2
    sr_limit = demand_feedin * sr_requirement

    rm_requirement = 0.4
    rm_limit = demand_feedin * rm_requirement

    constraints.spinning_reserve_constraint( m, sr_limit, groups=gen_set, storage=storage )

    # constraints.n1_constraint(m, demand_feedin, groups=gen_set)

    constraints.gen_order_constraint( m, groups=gen_set )

    constraints.rotating_mass_constraint( m, rm_limit, groups=gen_set, storage=storage )

    return [m, gen_set]


def solve_and_create_results(m, lp_write=False, gap=0.01):
    if lp_write == True:
        m.write( os.path.join( 'results', 'Lifuka.lp' ), io_options={'symbolic_solver_labels': True} )

    # solve with specific optimization options (passed to pyomo)
    logging.info( "Solve optimization problem" )

    m.solve( solver='gurobi', solve_kwargs={'tee':False}, cmdline_options={'MIPGap': gap} )

    # cmdline_options = {'MIPGap': 0.01}

    # write back results from optimization object to energysystem
    logging.info( 'Print results back to energysystem' )
    res = processing.results( m )

    return res


def sizing_results(results,m, sizing_list):
    res = {}

    for i in range( len( sizing_list ) ):
        node=m.es.groups[sizing_list[i]]
        node_data=views.node(results,node)
        for nodes, flow_name in node_data['sequences']:
            if 'scalars' in node_data and node_data['scalars'].get((nodes, 'invest')) is not None:
                res[nodes] = node_data['scalars'].get((nodes, 'invest'))

        df=pd.DataFrame.from_dict(res,orient='index')
    return df


def results_postprocessing(n, component_list, time_horizon=None):
    generator_list = []

    for i in range( len( component_list ) ):
        d1 = views.node( n, component_list[i] )['sequences']

        if time_horizon is not None:
            generator_list.append( d1.iloc[:time_horizon] )
        else:
            generator_list.append( d1 )

    res = pd.concat( generator_list, axis=1 )

    return res


def get_timeseries(file='data/timeseries.csv'):
    timeseries = pd.read_csv(file, sep=';' )
    timeseries.set_index( pd.DatetimeIndex( timeseries['timestamp'], freq='H' ), inplace=True )
    timeseries.drop( labels='timestamp', axis=1, inplace=True )
    timeseries[timeseries['PV'] > 1]['PV'] = 1
    return timeseries

