import pyomo.environ as po
from oemof.solph.options import Investment


def gen_order_constraint (m, groups=None):

    if groups is None:
        UserWarning('Rotating mass constraint cannot be built. groups is none')
        pass

    gen_max = []

    for n in groups:
        for (k, v) in n.electrical_output.items():
            gen_max += [v.nominal_value * v.max[0]]

    groups = [x for _, x in sorted(zip(gen_max, groups))]

    O = {n: [k for (k, v) in n.electrical_output.items()][0] for n in groups}

    def gen_order1_rule (m, t):
        expr = m.NonConvexFlow.status[groups[0], O[groups[0]], t] >= \
               m.NonConvexFlow.status[groups[1], O[groups[1]], t]
        return expr

    m.gen_order1 = po.Constraint(m.TIMESTEPS, rule=gen_order1_rule)

    #gen_order2 constraint can be turned on in case one wants to limit the operatiion of DG3 to operating intervals of
    #DG2
    #     expr = m.NonConvexFlow.status[groups[1], O[groups[1]], t] >= \
    #            m.NonConvexFlow.status[groups[2], O[groups[2]], t]
    #     return expr
    #
    # m.gen_order2 = po.Constraint(m.TIMESTEPS, rule=gen_order2_rule)

    return m


def rotating_mass_constraint (m, limit, groups=None, storage=None):

    if groups is None :
        UserWarning('Rotating mass constraint cannot be built. groups is none')
        pass

    gen_max = []

    for n in groups:
        for (k, v) in n.electrical_output.items():
            gen_max += [v.nominal_value * v.max[0]]

    groups = [x for _, x in sorted(zip(gen_max, groups))]

    if storage is not None and isinstance(storage.investment, Investment):
        rm_l_storage = m.GenericInvestmentStorageBlock.invest[storage] * storage.nominal_output_capacity_ratio

    elif storage is not None and not isinstance(storage.investment, Investment):
        rm_l_storage = storage.nominal_capacity * storage.nominal_output_capacity_ratio

    else:
        rm_l_storage = 0

    O = {n: [k for (k, v) in n.electrical_output.items()][0] for n in groups}

    def rotating_mass_l_rule (m, t):
        expr = sum([m.flow[n, O[n], t] for n in groups]) + \
               rm_l_storage\
               >= limit[t]
        return expr

    m.rotating_mass_l = po.Constraint(m.TIMESTEPS, rule=rotating_mass_l_rule)

    rm_u_storage = []

    if storage is not None and isinstance(storage.investment, Investment):
        for t in m.TIMESTEPS:
            rm_u_storage += [(m.GenericInvestmentStorageBlock.capacity[storage, t] -
                              m.GenericInvestmentStorageBlock.invest[storage] * storage.capacity_min[t]) *
                             storage.outflow_conversion_factor[t]]

    elif storage is not None and not isinstance(storage.investment, Investment):
        for t in m.TIMESTEPS:
            rm_u_storage += [(m.GenericStorageBlock.capacity[storage, t] -
                              storage.nominal_capacity * storage.capacity_min[t]) *
                             storage.outflow_conversion_factor[t]]
    else:
        for t in m.TIMESTEPS:
            rm_u_storage += [t*0]

    def rotating_mass_u_rule (m, t):
        expr = sum([m.flow[n, O[n], t] for n in groups]) + \
               rm_u_storage[t]\
               >= limit[t]
        return expr

    m.rotating_mass_u = po.Constraint(m.TIMESTEPS, rule=rotating_mass_u_rule)

    return m


def spinning_reserve_constraint (m, limit, groups=None, storage=None):

    if groups is None:
        UserWarning('Rotating mass constraint cannot be built. groups is none')
        pass

    gen_max = []

    for n in groups:
        for (k, v) in n.electrical_output.items():
            gen_max += [v.nominal_value * v.max[0]]

    groups = [x for _, x in sorted(zip(gen_max, groups))]

    O = {n: [k for (k, v) in n.electrical_output.items()][0] for n in groups}

    if storage is not None and isinstance(storage.investment, Investment):
        sr_l_storage = m.GenericInvestmentStorageBlock.invest[storage] * storage.nominal_output_capacity_ratio

    elif storage is not None and not isinstance(storage.investment, Investment):
        sr_l_storage = storage.nominal_capacity * storage.nominal_output_capacity_ratio

    else:
        sr_l_storage = 0

    def spinning_reserve_l_rule (m, t):

        expr = sum([m.NonConvexFlow.status[n, O[n], t] * m.flows[n, O[n]].max[t] *
                    m.flows[n, O[n]].nominal_value - m.flow[n, O[n], t] for n in groups]) \
               + sr_l_storage \
               >= limit[t]

        return expr

    m.spinning_reserve_l = po.Constraint(m.TIMESTEPS, rule=spinning_reserve_l_rule)

    sr_u_storage = []

    if storage is not None and isinstance(storage.investment , Investment):
        for t in m.TIMESTEPS:
            sr_u_storage += [(m.GenericInvestmentStorageBlock.capacity[storage, t] -
                              m.GenericInvestmentStorageBlock.invest[storage] * storage.capacity_min[t])
                             * storage.nominal_output_capacity_ratio]

    elif storage is not None and not isinstance(storage.investment , Investment):
        for t in m.TIMESTEPS:
            sr_u_storage += [(m.GenericStorageBlock.capacity[storage, t] -
                              storage.nominal_capacity * storage.capacity_min[t])
                             * storage.nominal_output_capacity_ratio]
    else:
        for t in m.TIMESTEPS:
            sr_u_storage += [t*0]

    def spinning_reserve_u_rule (m, t):
        expr = sum([m.NonConvexFlow.status[n, O[n], t] * m.flows[n, O[n]].max[t] *
                    m.flows[n, O[n]].nominal_value - m.flow[n, O[n], t] for n in groups])\
               + sr_u_storage[t]\
               >= limit[t]

        return expr

    m.spinning_reserve_u = po.Constraint(m.TIMESTEPS, rule=spinning_reserve_u_rule)

    return m


def n1_constraint (m, limit, groups=None):

    if groups is None:
        UserWarning('Rotating mass constraint cannot be built. groups is none')
        pass

    gen_max = []

    for n in groups:
        for (k, v) in n.electrical_output.items():
            gen_max += [v.nominal_value * v.max[0]]

    groups = [x for _, x in sorted(zip(gen_max, groups))]

    O = {n: [k for (k, v) in n.electrical_output.items()][0] for n in groups}

    def n1_rule (m, t):

        expr = sum([m.NonConvexFlow.status[n, O[n], t] * m.flows[n, O[n]].max[t] *
                    m.flows[n, O[n]].nominal_value for n in groups]) - \
               m.NonConvexFlow.status[groups[0], O[groups[0]], t] * m.flows[groups[0], O[groups[0]]].max[t] * \
               m.flows[groups[0], O[groups[0]]].nominal_value \
               >= limit[t] * m.NonConvexFlow.status[groups[0], O[groups[0]], t]
        return expr

    m.n1_constraint = po.Constraint(m.TIMESTEPS, rule=n1_rule)

    def n2_rule (m, t):
        expr = sum([m.NonConvexFlow.status[n, O[n], t] * m.flows[n, O[n]].max[t] *
                    m.flows[n, O[n]].nominal_value for n in groups]) - \
               m.NonConvexFlow.status[groups[1], O[groups[1]], t] * m.flows[groups[1], O[groups[1]]].max[t] * \
               m.flows[groups[1], O[groups[1]]].nominal_value \
               >= limit[t] * m.NonConvexFlow.status[groups[1], O[groups[1]], t]
        return expr

    m.n2_constraint = po.Constraint(m.TIMESTEPS, rule=n2_rule)

    def n3_rule (m, t):
        expr = sum([m.NonConvexFlow.status[n, O[n], t] * m.flows[n, O[n]].max[t] *
                    m.flows[n, O[n]].nominal_value for n in groups]) - \
               m.NonConvexFlow.status[groups[2], O[groups[2]], t] * m.flows[groups[2], O[groups[2]]].max[t] * \
               m.flows[groups[2], O[groups[2]]].nominal_value \
               >= limit[t] * m.NonConvexFlow.status[groups[2], O[groups[2]], t]
        return expr

    m.n3_constraint = po.Constraint(m.TIMESTEPS, rule=n3_rule)

    return m

