# ----------------------------------------------------------------------------
# Copyright (C) 2021 Deepchecks (https://www.deepchecks.com)
#
# This file is part of Deepchecks.
# Deepchecks is distributed under the terms of the GNU Affero General
# Public License (version 3 or later).
# You should have received a copy of the GNU Affero General Public License
# along with Deepchecks.  If not, see <http://www.gnu.org/licenses/>.
# ----------------------------------------------------------------------------
#
"""Common utilities for distribution checks."""

from typing import Tuple, Union, Hashable, Callable

from scipy.stats import wasserstein_distance
import numpy as np
import pandas as pd

from sklearn.impute import SimpleImputer

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from deepchecks.checks.distribution.plot import drift_score_bar_traces, feature_distribution_traces
from deepchecks.checks.distribution.preprocessing import preprocess_2_cat_cols_to_same_bins

PSI_MIN_PERCENTAGE = 0.01


__all__ = ['PandasSimpleImputer', 'preprocess_2_cat_cols_to_same_bins', 'psi', 'earth_movers_distance',
           'calc_drift_and_plot']


class PandasSimpleImputer(SimpleImputer):
    """A wrapper around `SimpleImputer` to return data frames with columns."""

    def fit(self, X, y=None):  # pylint: disable=C0103
        """Fit the imputer on X and return self."""
        self.columns = X.columns  # pylint: disable=C0103
        return super().fit(X, y)  # pylint: disable=C0103

    def transform(self, X):  # pylint: disable=C0103
        """Transform X using the imputer."""
        return pd.DataFrame(super().transform(X), columns=self.columns)  # pylint: disable=C0103


def psi(expected_percents: np.ndarray, actual_percents: np.ndarray):
    """
    Calculate the PSI (Population Stability Index).

    See https://www.lexjansen.com/wuss/2017/47_Final_Paper_PDF.pdf

    Args:
        expected_percents: array of percentages of each value in the expected distribution.
        actual_percents: array of percentages of each value in the actual distribution.

    Returns:
        psi: The PSI score

    """
    psi_value = 0
    for i in range(len(expected_percents)):
        # In order for the value not to diverge, we cap our min percentage value
        e_perc = max(expected_percents[i], PSI_MIN_PERCENTAGE)
        a_perc = max(actual_percents[i], PSI_MIN_PERCENTAGE)
        value = (e_perc - a_perc) * np.log(e_perc / a_perc)
        psi_value += value

    return psi_value


def earth_movers_distance(dist1: Union[np.ndarray, pd.Series], dist2: Union[np.ndarray, pd.Series]):
    """
    Calculate the Earth Movers Distance (Wasserstein distance).

    See https://en.wikipedia.org/wiki/Wasserstein_metric

    Function is for numerical data only.

    Args:
        dist1: array of numberical values.
        dist2: array of numberical values to compare dist1 to.

    Returns:
        the Wasserstein distance between the two distributions.

    """
    unique1 = np.unique(dist1)
    unique2 = np.unique(dist2)

    sample_space = list(set(unique1).union(set(unique2)))

    val_max = max(sample_space)
    val_min = min(sample_space)

    if val_max == val_min:
        return 0

    dist1 = (dist1 - val_min) / (val_max - val_min)
    dist2 = (dist2 - val_min) / (val_max - val_min)

    return wasserstein_distance(dist1, dist2)


def calc_drift_and_plot(train_column: pd.Series, test_column: pd.Series, plot_title: Hashable,
                        column_type: str, max_num_categories: int = 10) -> Tuple[float, str, Callable]:
    """
    Calculate drift score per column.

    Args:
        train_column: column from train dataset
        test_column: same column from test dataset
        plot_title: title of plot
        column_type: type of column (either "numerical" or "categorical")
        max_num_categories: Max number of allowed categories. If there are more, they are binned into an "Other"
                            category.

    Returns:
        score: drift score of the difference between the two columns' distributions (Earth movers distance for
        numerical, PSI for categorical)
        display: graph comparing the two distributions (density for numerical, stack bar for categorical)
    """
    train_dist = train_column.dropna().values.reshape(-1)
    test_dist = test_column.dropna().values.reshape(-1)

    if column_type == 'numerical':
        scorer_name = "Earth Mover's Distance"
        score = earth_movers_distance(dist1=train_column.astype('float'), dist2=test_column.astype('float'))
        bar_stop = max(0.4, score + 0.1)

        score_bar = drift_score_bar_traces(score)

        traces, xaxis_layout, yaxis_layout = feature_distribution_traces(train_dist, test_dist)

    elif column_type == 'categorical':
        scorer_name = 'PSI'
        expected_percents, actual_percents, _ = \
            preprocess_2_cat_cols_to_same_bins(dist1=train_dist, dist2=test_dist, max_num_categories=max_num_categories)
        score = psi(expected_percents=expected_percents, actual_percents=actual_percents)
        bar_stop = min(max(0.4, score + 0.1), 1)

        score_bar = drift_score_bar_traces(score)

        traces, xaxis_layout, yaxis_layout = feature_distribution_traces(train_dist, test_dist, is_categorical=True,
                                                                         max_num_categories=max_num_categories)

    fig = make_subplots(rows=2, cols=1, vertical_spacing=0.4, shared_yaxes=False, shared_xaxes=False,
                        row_heights=[0.1, 0.9],
                        subplot_titles=['Drift Score - ' + scorer_name, plot_title])

    fig.add_traces(score_bar, rows=[1] * len(score_bar), cols=[1] * len(score_bar))
    fig.add_traces(traces, rows=[2] * len(traces), cols=[1] * len(traces))

    shared_layout = go.Layout(
        xaxis=dict(
            showgrid=False,
            gridcolor='black',
            linecolor='black',
            range=[0, bar_stop],
            dtick=0.05
        ),
        yaxis=dict(
            showgrid=False,
            showline=False,
            showticklabels=False,
            zeroline=False,
        ),
        xaxis2=xaxis_layout,
        yaxis2=yaxis_layout,
        legend=dict(
            title='Dataset',
            yanchor='top',
            y=0.6),
        width=700,
        height=400
    )

    fig.update_layout(shared_layout)

    return score, scorer_name, fig
