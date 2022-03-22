__author__ = "Jarne Verhaeghe, Jeroen Van Der Donckt"

import shap
import pandas as pd
import numpy as np

from tqdm.auto import tqdm
from numpy.random import RandomState
from sklearn.model_selection import train_test_split
from abc import ABC

from typing import Any


class ShapExplainer(ABC):
    """Interface class for a (POWERshap explainer class."""

    def __init__(
        self,
        model: Any,
    ):
        """Create a POWERshap explainer instance.

        Parameters
        ----------
        model: Any
            The  model from which powershap will use its shap values to perform feature
            selection.

        """
        assert self.supports_model(model)
        self.model = model

    # Should be implemented by subclass
    def _fit_get_shap(self, X_train, Y_train, X_val, Y_val, random_seed) -> np.ndarray:
        raise NotImplementedError

    # Should be implemented by subclass
    @staticmethod
    def supports_model(model) -> bool:
        """Check whether the POWERshap explainer supports the given model.

        Parameters
        ----------
        model: Any
            The model.

        Returns
        -------
        bool
            True if the POWERshap expliner supports the given model, otherwise False.

        """
        raise NotImplementedError

    def explain(
        self,
        X: pd.DataFrame,  #     current_df,
        y: np.array,  #    target_column,
        # feature_columns_random=None,
        # index_column=None,
        loop_its: int,
        val_size: float,
        stratify=None,
        random_seed_start=0,
    ) -> pd.DataFrame:
        """Get the shap values,

        Parameters
        ----------
        X: pd.DataFrame
            The features.
        y: np.array
            The labels.
        loop_its: int
            The number of iterations to fit the model with random state and random
            feature.
        val_size: float
            The fractional size of the validation set. Should be a float between ]0,1[.
        """
        random_col_name = "random_uniform_feature"
        assert not random_col_name in X.columns

        X = X.copy(deep=True)

        # shaps = np.array([])  # TODO: pre-allocate for efficiency
        shaps = []

        for i in tqdm(range(loop_its)):
            npRandomState = RandomState(i + random_seed_start)

            # Add uniform random feature to X
            random_uniform_feature = npRandomState.uniform(-1, 1, len(X))
            X["random_uniform_feature"] = random_uniform_feature

            # Perform train-test split
            train_idx, val_idx = train_test_split(
                np.arange(len(X)),
                test_size=val_size,
                random_state=i,
                stratify=stratify,
            )
            X_train = X.iloc[train_idx]
            X_val = X.iloc[val_idx]
            Y_train = y[train_idx]
            Y_val = y[val_idx]

            Shap_values = self._fit_get_shap(
                X_train=X_train.values,
                Y_train=Y_train,
                X_val=X_val.values,
                Y_val=Y_val,
                random_seed=i + random_seed_start,
            )

            Shap_values = np.abs(Shap_values)

            # TODO: consider to convert to even float16?
            shaps += [np.mean(Shap_values, axis=0).astype("float32")]

        shaps = np.array(shaps)

        return pd.DataFrame(data=shaps, columns=X_train.columns.values)


### CATBOOST

from catboost import CatBoostRegressor, CatBoostClassifier


class CatboostExplainer(ShapExplainer):
    @staticmethod
    def supports_model(model) -> bool:
        supported_models = [CatBoostRegressor, CatBoostClassifier]
        return isinstance(model, tuple(supported_models))

    def _fit_get_shap(self, X_train, Y_train, X_val, Y_val, random_seed) -> np.array:
        # Fit the model
        PowerSHAP_model = self.model.copy().set_params(random_seed=random_seed)
        PowerSHAP_model.fit(X_train, Y_train, eval_set=(X_val, Y_val))
        # Calculate the shap values
        C_explainer = shap.TreeExplainer(PowerSHAP_model)
        return C_explainer.shap_values(X_val)


### RANDOMFOREST


class EnsembleExplainer(ShapExplainer):
    @staticmethod
    def supports_model(model) -> bool:
        # TODO: these first 2 require extra checks on the base_estimator
        # from sklearn.ensemble._weight_boosting import BaseWeightBoosting
        # from sklearn.ensemble._bagging import BaseBagging
        from sklearn.ensemble._forest import ForestRegressor, ForestClassifier
        from sklearn.ensemble._gb import BaseGradientBoosting

        supported_models = [ForestRegressor, ForestClassifier, BaseGradientBoosting]
        return isinstance(model, tuple(supported_models))

    def _fit_get_shap(self, X_train, Y_train, X_val, Y_val, random_seed) -> np.array:
        from sklearn.base import clone

        # Fit the model
        PowerSHAP_model = clone(self.model).set_params(random_state=random_seed)
        PowerSHAP_model.fit(X_train, Y_train)
        # Calculate the shap values
        C_explainer = shap.TreeExplainer(PowerSHAP_model)
        return C_explainer.shap_values(X_val)


### LINEAR


class LinearExplainer(ShapExplainer):
    @staticmethod
    def supports_model(model) -> bool:
        from sklearn.linear_model._base import LinearClassifierMixin, LinearModel
        from sklearn.linear_model._stochastic_gradient import BaseSGD

        supported_models = [LinearClassifierMixin, LinearModel, BaseSGD]
        return isinstance(model, tuple(supported_models))

    def _fit_get_shap(self, X_train, Y_train, X_val, Y_val, random_seed) -> np.array:
        from sklearn.base import clone

        # Fit the model
        try:
            PowerSHAP_model = clone(self.model).set_params(random_state=random_seed)
        except:
            PowerSHAP_model = clone(self.model)
        PowerSHAP_model.fit(X_train, Y_train)
        # Calculate the shap values
        C_explainer = shap.explainers.Linear(PowerSHAP_model, X_train)
        return C_explainer.shap_values(X_val)


### DEEP LEARNING


class DeepLearningExplainer(ShapExplainer):
    # TODO
    @staticmethod
    def supports_model(model) -> bool:
        import tensorflow as tf
        import torch

        supported_models = [tf.keras.Model, torch.nn.Module]
        return isinstance(model, tuple(supported_models))

    def _fit_get_shap(self, X_train, Y_train, X_val, Y_val, random_seed) -> np.ndarray:

        raise NotImplementedError  # TODO pass the model_kwargs
        # PowerSHAP_model = self.model
        # PowerSHAP_model.compile(
        #     loss=loss,
        #     optimizer=optimizer,
        #     metrics=[nn_metric],
        # )
        # _ = PowerSHAP_model.fit(X_train,Y_train, batch_size=batch_size, epochs=epochs, validation_data=(X_val_feat,Y_val),verbose=False)

        C_explainer = shap.DeepExplainer(PowerSHAP_model, X_train)

        return C_explainer.shap_values(X_val)[0]
