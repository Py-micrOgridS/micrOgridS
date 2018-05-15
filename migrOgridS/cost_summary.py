import pandas
from oemof.solph import Source
from oemof.solph.components import GenericStorage
from oemof.solph.custom import DieselGenerator
from oemof.outputlib import views


def get_lcoe_for_node (results, node):
    """
    Returns LCOE for current node split up into investment-, OPEX- and
    "fuel"-LCOE. Thereby, investment, OPEX and "fuel" costs are calculated as
    follows:
    - Investment is calculated by multiplication of all investments
    (input and output flow as well as node-internal investment) with their
    correlated ep_costs.
    - OPEX are derived from variable and fixed costs of all output flows
    as well as fixed costs from node itself (ie. in case of GenericStorage).
    - "Fuel" costs are calculated the same way as OPEX, but for all output
    flows respectively
    """

    def get_fixed_costs (component, nv):
        # nv is either invest or nominal_value of component:
        if nv is None:
            # Try to get nominal_value from component:
            nv = component.nominal_value
        try:
            return nv * component.fixed_costs
        except (AttributeError, TypeError):
            return 0.0

    def get_invest_costs (component, nv):
        try:
            return nv * component.investment.ep_costs
        except (AttributeError, TypeError):
            return 0.0

    def get_variable_costs (flow_comp, current_flow):
        variable_costs_factor = flow_comp.variable_costs.data
        if variable_costs_factor[0] is not None:
            variable_costs_factors = pandas.Series(variable_costs_factor)
            variable_costs_factors.reset_index(drop=True)
            return current_flow.mul(variable_costs_factors).sum()
        else:
            return 0.0

    if isinstance(node, str):
        raise TypeError('Node has to be a real node, not str')

    node_data = views.node(results, node)

    # Init costs and output:
    invest = 0.0
    opex = 0.0
    resource = 0.0
    output = 0.0

    for nodes, flow_name in node_data['sequences']:
        # Set invest_value if given:
        invest_value = None
        if 'scalars' in node_data:
            invest_value = node_data['scalars'].get((nodes, 'invest'))
        if len(nodes) == 1:
            # If only one node is given, flow_component is not given, instead
            # node itself is used to calculate investment and fixed costs:
            flow_component = nodes[0]
            opex += get_fixed_costs(nodes[0], invest_value)
        else:
            # Input flows are used for fuel cost calculation,
            # output flows are used for OPEX calculation
            try:
                flow = node_data['sequences'][(nodes, flow_name)]
                flow.reset_index(drop=True, inplace=True)

                if nodes[0] == node and nodes[1] == None:
                    flow_component = node

                elif nodes[0] == node:
                    output += flow.sum()
                    flow_component = node.outputs[nodes[1]]

                    if isinstance(node, GenericStorage):
                        opex += get_fixed_costs(flow_component, invest_value)
                    else:
                        opex += get_variable_costs(flow_component, flow)
                        opex += get_fixed_costs(flow_component, invest_value)

                else:
                    flow_component = node.inputs[nodes[0]]
                    resource += get_variable_costs(flow_component, flow)
                    resource += get_fixed_costs(flow_component, invest_value)

                invest += get_invest_costs(flow_component, invest_value)

            except (KeyError):
                pass

    return map(lambda x: x, [invest, opex, resource, output])


def get_lcoe_for_DG (results, node):
    """
    Returns LCOE for current node split up into investment-, OPEX- and
    "fuel"-LCOE for the EngineGenerator. This function is a slight modification
    of get_lcoe_for_nodes, as om_cost are defined for this objects that are
    dependent on the status variable at every time step

    Hence, investment, OPEX and "fuel" costs are calculated as
    follows:
    - Investment is calculated by multiplication of all investments
    (input and output flow as well as node-internal investment) with their
    correlated ep_costs.
    - OPEX are derived from om_costs and fixed costs of all output flows
    as well as fixed costs from node itself (ie. in case of GenericStorage).
    - "Fuel" costs are calculated the same way as OPEX, but for all input
    lows to the GenericEngine/DieselGenerator objects, respectively

    Parameters:
        results:    pd.DataFrame containig the results of the optimization achieved
                    by oemof.outputlib.processing.results()
        node:       node oemof.solph.m.es.node

    Returns:
        map(lambda x: x, [invest, om, resource, output]):dict containing [invest, om, resource, output]  mapped to cost


    """

    def get_variable_costs (flow_comp, current_flow):
        variable_costs_factor = flow_comp.variable_costs.data
        if variable_costs_factor[0] is not None:
            variable_costs_factors = pandas.Series(variable_costs_factor)
            variable_costs_factors.reset_index(drop=True)
            return current_flow.mul(variable_costs_factors).sum()
        else:
            return 0.0

    node_data = views.node(results, node)
    output = 0
    resource = 0
    invest = 0
    if isinstance(node, str):
        raise TypeError('Node has to be a real node, not str')

    for nodes, flow_name in node_data['sequences']:
        flow = node_data['sequences'][(nodes, flow_name)]
        flow.reset_index(drop=True, inplace=True)

        if nodes[0] == node:
            flow_component = node.outputs[nodes[1]]

            if flow_name == 'status':
                runtime_hours = flow.sum()
                om = flow_component.nonconvex.om_costs * runtime_hours * flow_component.nominal_value

            elif flow_name == 'flow':
                output += flow.sum()
                invest += flow_component.fixed_costs * flow_component.nominal_value

        else:
            flow_component = node.inputs[nodes[0]]
            resource += get_variable_costs(flow_component, flow)

    return map(lambda x: x, [invest, om, resource, output])


def get_lcoe (m, results, component_list):
    """

    Returns an output table as pd.DataFrame with the columns ['CAPEX','OPEX','fuel_cost','output'] and
    component labels as index.

    Parameters:
        m  :        operational model  oemof.solph.model object
        results :   pd.DataFrame containig the results of the optimization achieved
                    by oemof.outputlib.processing.results()
        component_list : list of component labels to be included in the output table

    Returns:
        economic results:   pd.DataFrame


    """
    economic_results = pandas.DataFrame(index=component_list, columns=['CAPEX', 'OPEX', 'fuel_cost', 'output'])

    for i in range(len(component_list)):
        node = m.es.groups[component_list[i]]

        if isinstance(node, DieselGenerator):
            n = economic_results.loc[component_list[i]]
            n[0], n[1], n[2], n[3] = get_lcoe_for_DG(results, node)

        elif isinstance(node, GenericStorage) or isinstance(node, Source):
            n = economic_results.loc[component_list[i]]
            n[0], n[1], n[2], n[3] = get_lcoe_for_node(results, node)
        else:
            economic_results.drop(labels=component_list[i], axis=0, inplace=True)

    return economic_results
