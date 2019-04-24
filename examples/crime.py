"""Crime prediction

The data is from: https://data.cityofchicago.org/Public-Safety/Crimes-2001-to-present/ijzp-q8t2.
"""

import os

import numpy as np
import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt
from sklearn.utils import shuffle
from sklearn.model_selection import train_test_split
from scipy.stats import poisson

import cvxstrat
from utils import latexify


# Download data and preprocess
if not os.path.exists('data/crimes.fea'):
    raw_df = pd.read_csv(
        'data/crimes.csv', low_memory=False, parse_dates=["Date"])
    raw_df.to_feather('data/crimes.fea')

raw_df = pd.read_feather('data/crimes.fea')

np.random.seed(0)
df = shuffle(raw_df.query('Year == 2017 | Year == 2018').copy())
attr = ['Year', 'Week', 'Dayofweek', 'Hour']
for n in attr:
    df[n] = getattr(df['Date'].dt, n.lower())
df.Latitude = pd.to_numeric(df.Latitude, errors='coerce')
df.Longitude = pd.to_numeric(df.Longitude, errors='coerce')
df = df[~np.isnan(df.Latitude)]
df = df[df.Longitude > -87.85]
bins = 20
df['lat_bin'] = pd.cut(df['Latitude'], bins=bins)
df['lon_bin'] = pd.cut(df['Longitude'], bins=bins)
code_to_latbin = dict(enumerate(df['lat_bin'].cat.categories))
code_to_longbin = dict(enumerate(df['lon_bin'].cat.categories))
df['lat_bin'] = df['lat_bin'].cat.codes
df['lon_bin'] = df['lon_bin'].cat.codes
df.drop(["Unnamed: 0", "ID", "Case Number", "Block", "Description", "Arrest",
         "Domestic", "Beat", "District", "Ward", "Community Area", "FBI Code",
         "X Coordinate", "Y Coordinate", "Updated On", "Location", "Date",
         "Primary Type", "Location Description", "IUCR"], axis=1, inplace=True, errors='ignore')

df_2017 = shuffle(df.query('Year == 2017'))
df_2018 = shuffle(df.query('Year == 2018'))
len(df_2017), len(df_2018)

del raw_df
del df

# Create regularization graph
G_location = nx.grid_2d_graph(bins, bins)
G_week = nx.cycle_graph(52)
G_day = nx.cycle_graph(7)
G_hour = nx.cycle_graph(24)
G = cvxstrat.cartesian_product([G_location, G_week, G_day, G_hour])
L = nx.laplacian_matrix(G)
K = L.shape[0]

print("Laplacian matrix:", repr(L))
del L

# Create dataset


def df_to_data(df):
    events = {}
    for node in G.nodes():
        events[node] = 0

    for _, r in df.iterrows():
        lat = int(r.lat_bin)
        lon = int(r.lon_bin)
        week = int(r.Week - 1)
        day = int(r.Dayofweek)
        hour = int(r.Hour)
        key = (lat, lon, week, day, hour)
        events[key] += 1

    Y = []
    Z = []
    for node in G.nodes():
        Y.append(events[node])
        Z.append(node)

    return Y, Z

Y_train, Z_train = df_to_data(df_2017)
Y_test, Z_test = df_to_data(df_2018)
print(len(Y_train), len(Y_test))
del G

# Fit models and evaluate log likelihood

kwargs = dict(rel_tol=1e-6, abs_tol=1e-6, maxiter=2000)
cvxstrat.set_edge_weight(G_location, 0)
cvxstrat.set_edge_weight(G_week, 0)
cvxstrat.set_edge_weight(G_day, 0)
cvxstrat.set_edge_weight(G_hour, 0)
G = cvxstrat.cartesian_product([G_location, G_week, G_day, G_hour])
fully = cvxstrat.Poisson()
info = fully.fit(Y_train, Z_train, G, **kwargs)
anll_train = fully.anll(Y_train, Z_train)
anll_test = fully.anll(Y_test, Z_test)
print("Fully")
print("\t", info)
print("\t", anll_train, anll_test)
del G

cvxstrat.set_edge_weight(G_location, 100)
cvxstrat.set_edge_weight(G_week, 100)
cvxstrat.set_edge_weight(G_day, 100)
cvxstrat.set_edge_weight(G_hour, 100)
G = cvxstrat.cartesian_product([G_location, G_week, G_day, G_hour])
strat = cvxstrat.Poisson()
info = strat.fit(Y_train, Z_train, G, **kwargs)
anll_train = strat.anll(Y_train, Z_train)
anll_test = strat.anll(Y_test, Z_test)
print("Strat")
print("\t", info)
print("\t", anll_train, anll_test)
del G

common = cvxstrat.Poisson()
info = common.fit(Y_train, [0] * len(Y_train), nx.empty_graph(1), **kwargs)
anll_train = common.anll(Y_train, [0] * len(Y_train))
anll_test = common.anll(Y_test, [0] * len(Y_test))
print("Common")
print("\t", info)
print("\t", anll_train, anll_test)

# Visualize and save figures
latexify(6)
params = np.array(
    [np.array([strat.G.nodes[loc + (i, j, k)]['theta']
               for i in range(G_week.order()) for j in range(G_day.order()) for k in range(G_hour.order())]).mean()
     for loc in G_location.nodes()]
)
lat = df_2017.Latitude
long = df_2017.Longitude
ticks = np.linspace(0, bins - 1, 5)
latrange = ["%.2f" % x for x in np.linspace(lat.max(), lat.min(), 5)]
longrange = ["%.2f" % x for x in np.linspace(long.min(), long.max(), 5)]
plt.imshow(params.reshape(bins, bins)[::-1, :])
plt.yticks(ticks, latrange)
plt.xticks(ticks, longrange)
plt.colorbar()
plt.savefig('./figs/crime_loc.pdf')
plt.close()

params = np.array(
    [[strat.G.nodes[loc + (i, j, k)]['theta']
      for i in range(G_week.order())] for j in range(G_day.order()) for k in range(G_hour.order()) for loc in G_location.nodes()])
params = params.mean(axis=0)

months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
plt.plot(params)
for i in range(12):
    plt.axvline(i * 4.2, c='black', alpha=.3)
plt.xticks(np.arange(12) * 4.2, months)
plt.savefig('./figs/crime_week.pdf')
plt.close()

params = np.array(
    [[strat.G.nodes[loc + (i, j, k)]['theta']
      for k in range(G_hour.order())
      for j in range(G_day.order())] for i in range(G_week.order()) for loc in G_location.nodes()])
params = params.mean(axis=0)

days = ['M', 'Tu', 'W', 'Th', 'F', 'Sa', 'Su']
plt.plot(params)
for i in range(7):
    plt.axvline(i * 24, c='black', alpha=.3)
plt.xticks(np.arange(7) * 24, days)
plt.savefig('./figs/crime_day.pdf')
plt.close()
