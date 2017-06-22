"""Streaming metrics implementation."""

import tensorflow as tf

from liteflow import streaming
from liteflow import utils

class StreamingMetric(streaming.StreamingComputation):
    """Streaming metric base class.

    This class implements the basic infrastructure to build a streaming
    average based evaluation metric. It works wrapping a function accepting
    as arguments the ground truth values, the predicted values and a weight tensor,
    and returning a tensor and a (possibly different) weight tensor to be used as
    the streaming average weighting. Such tensors will be averaged with a
    liteflow.streaming.StreamingAverage instance.

    The class has a method `compute` that builds the computational graph in charge
    of computing the streaming metric. Such method accepts the following arguments:
      targets: a `Tensor` representing the ground truth values.
      predictions: a `Tensor` representing the predicted values.
      weights: optional `Tensor` to weight the metric.
      metrics_collections: a list of string representing the keys of the collections
        to which the `Tensor` in `self.value` must be added.
      updates_collections: a list of string representing the keys of the collections
        to which the `Op` in `self.update_op` must be added.,
      scope: the variable scope name to be used to build the portion of the graph.

    The class implements also a __call__ interface that accepts the same arguments
    as the `compute()` method and returns a pair of:
      mean: a `Tensor` representing the current mean, which is a reference
        to `self.value`.
      update_op: an `Op` that updates the streaming value, which is a reference
        to `self.update_op`.

    This makes the class perfectly compliant to a standard function from `tf.metric`.

    Remarks:
      the `targets`, `predictions` and `weights` argument of both the `compute()` method
      and the `__call__` interface will be passed as-is to the wrapped function, so all
      the constraint on their type, shape, ecc. will have to be defined in the function
      itself.

    Example:
    ```python

    def someones_metric(targets, predictions, weights=None):
        # do something
        values = ...
        # possibly change the weighting scheme for the streaming average
        weights = ...
        return values, weights

    metric = StreamingMetric(
        func=someones_metric,
        average=liteflow.streaming.StreamingAverage())

    targets = ...
    predictions = ...
    weights = ...
    metric.compute(targets, predictions, weights)

    # or, in alternative:
    mean, update = metric(targets, predictions, weights)
    ```
    """

    def __init__(self, func, average=None, name=None):
        super(StreamingMetric, self).__init__(name=name)
        self._func = func
        self._avg = average or streaming.StreamingAverage()

    @property
    def value(self):
        """The current value of the metric."""
        return self._avg.value

    @property
    def count(self):
        """The number of elements seen so far."""
        return self._avg.count

    @property
    def total(self):
        """The total values of the metric summed up so far."""
        return self._avg.value

    @property
    def batch_value(self):
        """The value of the metric for the current batch."""
        return self._avg.batch_value

    @property
    def batch_count(self):
        """The number of elements in the current batch."""
        return self._avg.batch_count

    @property
    def batch_total(self):
        """The total value of the metric summed up for the current batch."""
        return self._avg.batch_total

    @property
    def update_op(self):
        """Updates the current value of the metric."""
        return self._avg.update_op

    @property
    def reset_op(self):
        """Reset the streaming computation of the metric."""
        return self._avg.reset_op

    def compute(self, targets, predictions, weights,
                metrics_collections=None,
                updates_collections=None,
                scope=None):
        """Build the computational graph portion to compute the streaming metric.

        Arguments:
          targets: a `Tensor` representing the gold truth values.
          predictions: a `Tensor` representing the predicted values.
          weights: optional `Tensor` to weight the metric.
          metrics_collections: a list of string representing the keys of the collections
            to which the `Tensor` in `self.value` must be added.
          updates_collections: a list of string representing the keys of the collections
            to which the `Op` in `self.update_op` must be added.,
          scope: the variable scope name to be used to build the portion of the graph.
        """
        # pylint: disable=I0011,E1129
        with tf.variable_scope(scope or self._name) as scope:
            values, weights = self._func(targets, predictions, weights)
            self._avg.compute(values, weights, scope=scope)

        if metrics_collections:
            utils.add_to_collections(metrics_collections, self.value)

        if updates_collections:
            utils.add_to_collections(updates_collections, self.update_op)

    # pylint: disable=I0011,W0221
    def __call__(self, targets, predictions, weights,
                 metrics_collections=None,
                 updates_collections=None,
                 scope=None):
        """Build the computational graph portion to compute the streaming metric.

        Arguments:
          targets: a `Tensor` representing the gold truth values.
          predictions: a `Tensor` representing the predicted values.
          weights: optional `Tensor` to weight the metric.
          metrics_collections: a list of string representing the keys of the collections
            to which the `Tensor` in `self.value` must be added.
          updates_collections: a list of string representing the keys of the collections
            to which the `Op` in `self.update_op` must be added.,
          scope: the variable scope name to be used to build the portion of the graph.

        Returns:
          mean: a `Tensor` representing the current mean.
          update_op: an `Op` that updates the streaming value.
        """
        self.compute(targets, predictions, weights,
                     metrics_collections=metrics_collections,
                     updates_collections=updates_collections,
                     scope=scope)
        return self.value, self.update_op


def accuracy(targets, predictions, weights):
    """Computes the categorical accuracy.

    Arguments:
      target: the gold truth values `Tensor`, with `tf.int32` as `dtype`. It has rank
        `[d_0, d_1, ..., d_{r-1}]` and the last value is supposed to range between
        `0` and `num_classes - 1`, where `num_classes` is the number of possible classes.
      predictions: the predicted values `Tensor` with `tf.float32` as `dtype`. It can
        have shape `[d_0, d_1, ..., d_{r-1}, num_classes]` and dtype `float32` and
        represents the probability distribution across the output classes generated by
        the model. Alternatively it can be of the same shape, `dtype` and format of `target`,
        and it will considered as the predicted labels.
      weights: coefficients for the loss. This must be scalar or of same rank as `target`.

    Returns:
      values: a `Tensor` of `dtype=tf.float32` and of the same shape as `targest`
        representing the accuracy, weighted according to the input argument `weights`.
      weights: a `Tensor` of `dtype=tf.float32` and of the same shape of `values`
        representing the weighted scheme for the streaming average on `values`, which
        is the same tensor of the input `weights` argument.
    """
    trank = targets.get_shape().ndims
    prank = predictions.get_shape().ndims
    if prank > trank:
        diff = prank - trank
        if diff > 1:
            raise ValueError(
                """Rank of `predictions` must be equal to rank of `label` """
                """or greater of 1, found %d and %d instead.""" % (prank, trank))
        predictions = tf.argmax(predictions, axis=-1)  # tf.int64!!!
        predictions = tf.cast(predictions, tf.int32)

    is_equal = tf.equal(targets, predictions)
    is_equal = tf.cast(is_equal, tf.float32)
    is_equal = tf.multiply(is_equal, weights)
    return is_equal, weights
