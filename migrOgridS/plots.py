import pandas as pd
import matplotlib.pyplot as plt


def unit_commitment_plot(filename, title=None, date_from=None, date_to=None):

    legend = {"(('electricity', 'demand'), 'flow')": 'load',
              "(('PV', 'electricity_dc'), 'flow')": 'PV',
              "(('electricity_dc', 'storage'), 'flow')": 'storage_in',
              "(('storage', 'None'), 'capacity')": 'storage_cap',
              "(('storage', 'electricity_dc'), 'flow')": 'storage_out',
              "(('pp_oil_1', 'electricity'), 'flow')": 'dg1',
              "(('pp_oil_2', 'electricity'), 'flow')": 'dg2',
              "(('pp_oil_3', 'electricity'), 'flow')": 'dg3',
              "(('electricity', 'excess'), 'flow')":'excess'}

    df = pd.read_csv( filename )
    df.set_index( pd.DatetimeIndex( df['timestamp'], freq='H' ), inplace=True )
    df.drop( 'timestamp', axis=1, inplace=True )


    if date_from is None:
        date_from = df.index[0]
    if date_to is None:
        date_to = df.index[-1]

    if isinstance( date_from, int ) and isinstance( date_to, int ):
        df = df.iloc[date_from:date_to]
    else:
        df = df.loc[date_from:date_to]
    order = []
    for i in list( df.columns.values ):

        if ('flow' in i or 'capacity' in i) and 'diesel_source' not in i:
            order += [i]
    df = df[order]
    df.rename( columns=legend, inplace=True )

    fig = plt.figure(figsize=(8,6))

    ax = fig.add_subplot( 1, 1, 1 )
    df.plot( linewidth=1.5, stacked=False, ax=ax )
    handles, labels = ax.get_legend_handles_labels()
    ax.legend( handles, labels, bbox_to_anchor=(1.05, 1), loc=2, borderaxespad=0. )
    ax.set_ylabel('power flow [kW]')
    ax.set_xlabel('datetime in hourly steps')
    ax.set_title(title)
    plt.show()

    return df

