# License: BSD 3 clause
"""
Tests related to classification experiments.

:author: Michael Heilman (mheilman@ets.org)
:author: Nitin Madnani (nmadnani@ets.org)
:author: Dan Blanchard (dblanchard@ets.org)
:author: Aoife Cahill (acahill@ets.org)
"""

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import csv
import glob
import itertools
import json
import os
import re
import sys
import warnings

from io import open
from os.path import abspath, dirname, exists, join

import numpy as np
from nose.tools import eq_, assert_almost_equal, raises

from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import accuracy_score

from skll.data import FeatureSet
from skll.data.readers import NDJReader
from skll.data.writers import NDJWriter
from skll.config import _parse_config_file
from skll.experiments import run_configuration
from skll.learner import Learner, _train_and_score
from skll.learner import _DEFAULT_PARAM_GRIDS

from utils import (make_classification_data, make_regression_data,
                   make_sparse_data, fill_in_config_paths_for_single_file)


_ALL_MODELS = list(_DEFAULT_PARAM_GRIDS.keys())
_my_dir = abspath(dirname(__file__))


def setup():
    train_dir = join(_my_dir, 'train')
    if not exists(train_dir):
        os.makedirs(train_dir)
    test_dir = join(_my_dir, 'test')
    if not exists(test_dir):
        os.makedirs(test_dir)
    output_dir = join(_my_dir, 'output')
    if not exists(output_dir):
        os.makedirs(output_dir)


def tearDown():
    train_dir = join(_my_dir, 'train')
    test_dir = join(_my_dir, 'test')
    output_dir = join(_my_dir, 'output')
    config_dir = join(_my_dir, 'configs')

    if exists(join(train_dir, 'train_single_file.jsonlines')):
        os.unlink(join(train_dir, 'train_single_file.jsonlines'))

    if exists(join(test_dir, 'test_single_file.jsonlines')):
        os.unlink(join(test_dir, 'test_single_file.jsonlines'))

    if exists(join(output_dir, 'rare_class_predictions.tsv')):
        os.unlink(join(output_dir, 'rare_class_predictions.tsv'))

    if exists(join(output_dir, 'float_class_predictions.tsv')):
        os.unlink(join(output_dir, 'float_class_predictions.tsv'))

    for output_file in glob.glob(join(output_dir, 'train_test_single_file_*')):
        os.unlink(output_file)

    config_files = [join(config_dir, cfgname) for cfgname in ['test_single_file.cfg',
                                                              'test_single_file_saved_subset']]
    for config_file in config_files:
        if exists(config_file):
            os.unlink(config_file)


def check_predict(model, use_feature_hashing=False):
    """
    This tests whether predict task runs and generates the same
    number of predictions as samples in the test set. The specified
    model indicates whether to generate random regression
    or classification data.
    """

    # create the random data for the given model
    if model._estimator_type == 'regressor':
        train_fs, test_fs, _ = \
            make_regression_data(use_feature_hashing=use_feature_hashing,
                                 feature_bins=5)
    # feature hashing will not work for Naive Bayes since it requires
    # non-negative feature values
    elif model.__name__ == 'MultinomialNB':
        train_fs, test_fs = \
            make_classification_data(use_feature_hashing=False,
                                     non_negative=True)
    else:
        train_fs, test_fs = \
            make_classification_data(use_feature_hashing=use_feature_hashing,
                                     feature_bins=25)

    # create the learner with the specified model
    learner = Learner(model.__name__)

    # now train the learner on the training data and use feature hashing when
    # specified and when we are not using a Naive Bayes model
    learner.train(train_fs, grid_search=False)

    # now make predictions on the test set
    predictions = learner.predict(test_fs)

    # make sure we have the same number of outputs as the
    # number of test set samples
    eq_(len(predictions), test_fs.features.shape[0])


def test_default_param_grids_no_duplicates():
    """
    Verify that the default parameter grids don't contain duplicate values.
    """
    for learner, param_list in _DEFAULT_PARAM_GRIDS.items():
        param_dict = param_list[0]
        for param_name, values in param_dict.items():
            assert(len(set(values)) == len(values))


# the runner function for the prediction tests
def test_predict():
    for model, use_feature_hashing in \
            itertools.product(_ALL_MODELS, [True, False]):
        yield check_predict, model, use_feature_hashing


# test predictions when both the model and the data use DictVectorizers
def test_predict_dict_dict():
    train_file = join(_my_dir, 'other', 'examples_train.jsonlines')
    test_file = join(_my_dir, 'other', 'examples_test.jsonlines')
    train_fs = NDJReader.for_path(train_file).read()
    test_fs = NDJReader.for_path(test_file).read()
    learner = Learner('LogisticRegression')
    learner.train(train_fs, grid_search=False)
    predictions = learner.predict(test_fs)
    eq_(len(predictions), test_fs.features.shape[0])


# test predictions when both the model and the data use FeatureHashers
# and the same number of bins
def test_predict_hasher_hasher_same_bins():
    train_file = join(_my_dir, 'other', 'examples_train.jsonlines')
    test_file = join(_my_dir, 'other', 'examples_test.jsonlines')
    train_fs = NDJReader.for_path(train_file, feature_hasher=True, num_features=3).read()
    test_fs = NDJReader.for_path(test_file, feature_hasher=True, num_features=3).read()
    learner = Learner('LogisticRegression')
    learner.train(train_fs, grid_search=False)
    predictions = learner.predict(test_fs)
    eq_(len(predictions), test_fs.features.shape[0])


# test predictions when both the model and the data use FeatureHashers
# but different number of bins
@raises(RuntimeError)
def test_predict_hasher_hasher_different_bins():
    train_file = join(_my_dir, 'other', 'examples_train.jsonlines')
    test_file = join(_my_dir, 'other', 'examples_test.jsonlines')
    train_fs = NDJReader.for_path(train_file, feature_hasher=True, num_features=3).read()
    test_fs = NDJReader.for_path(test_file, feature_hasher=True, num_features=2).read()
    learner = Learner('LogisticRegression')
    learner.train(train_fs, grid_search=False)
    _ = learner.predict(test_fs)


# test predictions when model uses a FeatureHasher and data
# uses a DictVectorizer
def test_predict_hasher_dict():
    train_file = join(_my_dir, 'other', 'examples_train.jsonlines')
    test_file = join(_my_dir, 'other', 'examples_test.jsonlines')
    train_fs = NDJReader.for_path(train_file, feature_hasher=True, num_features=3).read()
    test_fs = NDJReader.for_path(test_file).read()
    learner = Learner('LogisticRegression')
    learner.train(train_fs, grid_search=False)
    predictions = learner.predict(test_fs)
    eq_(len(predictions), test_fs.features.shape[0])


# test predictions when model uses a DictVectorizer and data
# uses a FeatureHasher
@raises(RuntimeError)
def test_predict_dict_hasher():
    train_file = join(_my_dir, 'other', 'examples_train.jsonlines')
    test_file = join(_my_dir, 'other', 'examples_test.jsonlines')
    train_fs = NDJReader.for_path(train_file).read()
    test_fs = NDJReader.for_path(test_file, feature_hasher=True, num_features=3).read()
    learner = Learner('LogisticRegression')
    learner.train(train_fs, grid_search=False)
    _ = learner.predict(test_fs)


# the function to create data with rare labels for cross-validation
def make_rare_class_data():
    """
    We want to create data that has five instances per class, for three labels
    and for each instance within the group of 5, there's only a single feature
    firing
    """

    ids = ['EXAMPLE_{}'.format(n) for n in range(1, 16)]
    y = [0] * 5 + [1] * 5 + [2] * 5
    X = np.vstack([np.identity(5), np.identity(5), np.identity(5)])
    feature_names = ['f{}'.format(i) for i in range(1, 6)]
    features = []
    for row in X:
        features.append(dict(zip(feature_names, row)))

    return FeatureSet('rare-class', ids, features=features, labels=y)


def test_rare_class():
    """
    Test cross-validation when some labels are very rare
    """

    rare_class_fs = make_rare_class_data()
    prediction_prefix = join(_my_dir, 'output', 'rare_class')
    learner = Learner('LogisticRegression')
    learner.cross_validate(rare_class_fs,
                           grid_objective='unweighted_kappa',
                           prediction_prefix=prediction_prefix)

    with open(prediction_prefix + '_predictions.tsv', 'r') as f:
        reader = csv.reader(f, dialect='excel-tab')
        next(reader)
        pred = [row[1] for row in reader]

        eq_(len(pred), 15)


def check_sparse_predict(learner_name, expected_score, use_feature_hashing=False):
    train_fs, test_fs = make_sparse_data(
        use_feature_hashing=use_feature_hashing)

    # train the given classifier on the training
    # data and evalute on the testing data
    learner = Learner(learner_name)
    learner.train(train_fs, grid_search=False)
    test_score = learner.evaluate(test_fs)[1]
    assert_almost_equal(test_score, expected_score)


def test_sparse_predict():
    for learner_name, expected_scores in zip(['LogisticRegression',
                                              'DecisionTreeClassifier',
                                              'RandomForestClassifier',
                                              'AdaBoostClassifier',
                                              'MultinomialNB',
                                              'KNeighborsClassifier',
                                              'RidgeClassifier',
                                              'MLPClassifier'],
                                             [(0.45, 0.52), (0.52, 0.5),
                                              (0.48, 0.5), (0.49, 0.5),
                                              (0.43, 0), (0.53, 0.57),
                                              (0.49, 0.49), (0.5, 0.49)]):
        yield check_sparse_predict, learner_name, expected_scores[0], False
        if learner_name != 'MultinomialNB':
            yield check_sparse_predict, learner_name, expected_scores[1], True


def test_mlp_classification():
    train_fs, test_fs = make_classification_data(num_examples=600,
                                                 train_test_ratio=0.8,
                                                 num_labels=3,
                                                 num_features=5)

    # train an MLPCLassifier on the training data and evalute on the
    # testing data
    learner = Learner('MLPClassifier')
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', category=ConvergenceWarning)
        learner.train(train_fs, grid_search=False)

    # now generate the predictions on the test set
    predictions = learner.predict(test_fs)

    # now make sure that the predictions are close to
    # the actual test FeatureSet labels that we generated
    # using make_regression_data. To do this, we just
    # make sure that they are correlated
    accuracy = accuracy_score(predictions, test_fs.labels)
    assert_almost_equal(accuracy, 0.858, places=3)


def check_sparse_predict_sampler(use_feature_hashing=False):
    train_fs, test_fs = make_sparse_data(
        use_feature_hashing=use_feature_hashing)

    if use_feature_hashing:
        sampler = 'RBFSampler'
        sampler_parameters = {"gamma": 1.0, "n_components": 50}
    else:
        sampler = 'Nystroem'
        sampler_parameters = {"gamma": 1.0, "n_components": 50,
                              "kernel": 'rbf'}

    learner = Learner('LogisticRegression',
                      sampler=sampler,
                      sampler_kwargs=sampler_parameters)

    learner.train(train_fs, grid_search=False)
    test_score = learner.evaluate(test_fs)[1]

    expected_score = 0.48 if use_feature_hashing else 0.45
    assert_almost_equal(test_score, expected_score)


def check_dummy_classifier_predict(model_args, train_labels, expected_output):

    # create hard-coded featuresets based with known labels
    train_fs = FeatureSet('classification_train',
                          ['TrainExample{}'.format(i) for i in range(20)],
                          labels=train_labels,
                          features=[{"feature": i} for i in range(20)])

    test_fs = FeatureSet('classification_test',
                         ['TestExample{}'.format(i) for i in range(10)],
                         features=[{"feature": i} for i in range(20, 30)])

    # Ensure predictions are as expectedfor the given strategy
    learner = Learner('DummyClassifier', model_kwargs=model_args)
    learner.train(train_fs, grid_search=False)
    predictions = learner.predict(test_fs)
    eq_(np.array_equal(expected_output, predictions), True)


def test_dummy_classifier_predict():

    # create a known set of labels
    train_labels = ([0] * 14) + ([1] * 6)
    for (model_args, expected_output) in zip([{"strategy": "stratified"},
                                              {"strategy": "most_frequent"},
                                              {"strategy": "constant", "constant": 1}],
                                             [np.array([0, 0, 0, 1, 0, 1, 1, 0, 0, 0]),
                                              np.zeros(10),
                                              np.ones(10)*1]):
        yield check_dummy_classifier_predict, model_args, train_labels, expected_output


def test_sparse_predict_sampler():
    yield check_sparse_predict_sampler, False
    yield check_sparse_predict_sampler, True


def make_single_file_featureset_data():
    """
    Write a training file and a test file for tests that check whether
    specifying train_file and test_file actually works.
    """
    train_fs, test_fs = make_classification_data(num_examples=600,
                                                 train_test_ratio=0.8,
                                                 num_labels=2,
                                                 num_features=3,
                                                 non_negative=False)

    # Write training feature set to a file
    train_path = join(_my_dir, 'train', 'train_single_file.jsonlines')
    writer = NDJWriter(train_path, train_fs)
    writer.write()

    # Write test feature set to a file
    test_path = join(_my_dir, 'test', 'test_single_file.jsonlines')
    writer = NDJWriter(test_path, test_fs)
    writer.write()

    # Also write another test feature set that has fewer features than the training set
    test_fs.filter(features=['f01', 'f02'])
    test_path = join(_my_dir, 'test', 'test_single_file_subset.jsonlines')
    writer = NDJWriter(test_path, test_fs)
    writer.write()


def test_train_file_test_file():
    """
    Test that train_file and test_file experiments work
    """
    # Create data files
    make_single_file_featureset_data()

    # Run experiment
    config_path = fill_in_config_paths_for_single_file(join(_my_dir, "configs",
                                                            "test_single_file"
                                                            ".template.cfg"),
                                                       join(_my_dir, 'train',
                                                            'train_single_file'
                                                            '.jsonlines'),
                                                       join(_my_dir, 'test',
                                                            'test_single_file.'
                                                            'jsonlines'))
    run_configuration(config_path, quiet=True)

    # Check results for objective functions ["accuracy", "f1"]

    # objective function accuracy
    with open(join(_my_dir, 'output', ('train_test_single_file_train_train_'
                                       'single_file.jsonlines_test_test_single'
                                       '_file.jsonlines_RandomForestClassifier'
                                       '_accuracy.results.json'))) as f:
        result_dict = json.load(f)[0]
    assert_almost_equal(result_dict['score'], 0.95)

    # objective function f1
    with open(join(_my_dir, 'output', ('train_test_single_file_train_train_'
                                       'single_file.jsonlines_test_test_single'
                                       '_file.jsonlines_RandomForestClassifier'
                                       '_f1.results.json'))) as f:
        result_dict = json.load(f)[0]
    assert_almost_equal(result_dict['score'], 0.9491525423728813)


def test_predict_on_subset_with_existing_model():
    """
    Test generating predictions on subset with existing model
    """
    # Create data files
    make_single_file_featureset_data()

    # train and save a model on the training file
    train_fs = NDJReader.for_path(join(_my_dir, 'train', 'train_single_file.jsonlines')).read()
    learner = Learner('RandomForestClassifier')
    learner.train(train_fs, grid_search=True, grid_objective="accuracy")
    model_filename = join(_my_dir, 'output', ('train_test_single_file_train_train_'
                                              'single_file.jsonlines_test_test_single'
                                              '_file_subset.jsonlines_RandomForestClassifier'
                                              '.model'))

    learner.save(model_filename)

    # Run experiment
    config_path = fill_in_config_paths_for_single_file(join(_my_dir, "configs",
                                                            "test_single_file_saved_subset"
                                                            ".template.cfg"),
                                                       join(_my_dir, 'train', 'train_single_file.jsonlines'),
                                                       join(_my_dir, 'test',
                                                            'test_single_file_subset.'
                                                            'jsonlines'))
    run_configuration(config_path, quiet=True, overwrite=False)

    # Check results
    with open(join(_my_dir, 'output', ('train_test_single_file_train_train_'
                                       'single_file.jsonlines_test_test_single'
                                       '_file_subset.jsonlines_RandomForestClassifier'
                                       '.results.json'))) as f:
        result_dict = json.load(f)[0]
    assert_almost_equal(result_dict['accuracy'], 0.7333333)


def test_train_file_test_file_ablation():
    """
    Test that specifying ablation with train and test file is ignored
    """
    # Create data files
    make_single_file_featureset_data()

    # Run experiment
    config_path = fill_in_config_paths_for_single_file(join(_my_dir, "configs",
                                                            "test_single_file"
                                                            ".template.cfg"),
                                                       join(_my_dir, 'train',
                                                            'train_single_file'
                                                            '.jsonlines'),
                                                       join(_my_dir, 'test',
                                                            'test_single_file.'
                                                            'jsonlines'))
    run_configuration(config_path, quiet=True, ablation=None)

    # check that we see the message that ablation was ignored in the experiment log
    # Check experiment log output
    with open(join(_my_dir,
                   'output',
                   'train_test_single_file.log')) as f:
        cv_file_pattern = re.compile('Not enough featuresets for ablation. Ignoring.')
        matches = re.findall(cv_file_pattern, f.read())
        eq_(len(matches), 1)


@raises(ValueError)
def test_train_file_and_train_directory():
    """
    Test that train_file + train_directory = ValueError
    """
    # Run experiment
    config_path = fill_in_config_paths_for_single_file(join(_my_dir, "configs",
                                                            "test_single_file"
                                                            ".template.cfg"),
                                                       join(_my_dir, 'train',
                                                            'train_single_file'
                                                            '.jsonlines'),
                                                       join(_my_dir, 'test',
                                                            'test_single_file.'
                                                            'jsonlines'),
                                                       train_directory='foo')
    _parse_config_file(config_path)


@raises(ValueError)
def test_test_file_and_test_directory():
    """
    Test that test_file + test_directory = ValueError
    """
    # Run experiment
    config_path = fill_in_config_paths_for_single_file(join(_my_dir, "configs",
                                                            "test_single_file"
                                                            ".template.cfg"),
                                                       join(_my_dir, 'train',
                                                            'train_single_file'
                                                            '.jsonlines'),
                                                       join(_my_dir, 'test',
                                                            'test_single_file.'
                                                            'jsonlines'),
                                                       test_directory='foo')
    _parse_config_file(config_path)


def check_adaboost_predict(base_estimator, algorithm, expected_score):
    train_fs, test_fs = make_sparse_data()

    # train an AdaBoostClassifier on the training data and evalute on the
    # testing data
    learner = Learner('AdaBoostClassifier', model_kwargs={'base_estimator': base_estimator,
                                                          'algorithm': algorithm})
    learner.train(train_fs, grid_search=False)
    test_score = learner.evaluate(test_fs)[1]
    assert_almost_equal(test_score, expected_score)


def test_adaboost_predict():
    for base_estimator_name, algorithm, expected_score in zip(['MultinomialNB',
                                                               'DecisionTreeClassifier',
                                                               'SGDClassifier',
                                                               'SVC'],
                                                              ['SAMME.R', 'SAMME.R',
                                                               'SAMME', 'SAMME'],
                                                              [0.46, 0.52, 0.45, 0.5]):
        yield check_adaboost_predict, base_estimator_name, algorithm, expected_score


def check_results_with_unseen_labels(res, n_labels, new_label_list):
    (confusion_matrix,
     score,
     result_dict,
     model_params,
     grid_score,
     additional_scores) = res

    # check that the new label is included into the results
    for output in [confusion_matrix, result_dict]:
        eq_(len(output), n_labels)

    # check that any additional metrics are zero
    eq_(additional_scores, {})

    # check that all metrics for new label are 0
    for label in new_label_list:
        for metric in ['Precision', 'Recall', 'F-measure']:
            eq_(result_dict[label][metric], 0)


def test_new_labels_in_test_set():
    """
    Test classification experiment with an unseen label in the test set.
    """
    train_fs, test_fs = make_classification_data(num_labels=3,
                                                 train_test_ratio=0.8)
    # add new labels to the test set
    test_fs.labels[-3:] = 3

    learner = Learner('SVC')
    learner.train(train_fs, grid_search=False)
    res = learner.evaluate(test_fs)
    yield check_results_with_unseen_labels, res, 4, [3]
    yield assert_almost_equal, res[1], 0.3


def test_new_labels_in_test_set_change_order():
    """
    Test classification with an unseen label in the test set when the new label falls between the existing labels
    """
    train_fs, test_fs = make_classification_data(num_labels=3,
                                                 train_test_ratio=0.8)
    # change train labels to create a gap
    train_fs.labels = train_fs.labels * 10
    # add new test labels
    test_fs.labels = test_fs.labels * 10
    test_fs.labels[-3:] = 15

    learner = Learner('SVC')
    learner.train(train_fs, grid_search=False)
    res = learner.evaluate(test_fs)
    yield check_results_with_unseen_labels, res, 4, [15]
    yield assert_almost_equal, res[1], 0.3


def test_all_new_labels_in_test():
    """
    Test classification with all labels in test set unseen
    """
    train_fs, test_fs = make_classification_data(num_labels=3,
                                                 train_test_ratio=0.8)
    # change all test labels
    test_fs.labels = test_fs.labels + 3

    learner = Learner('SVC')
    learner.train(train_fs, grid_search=False)
    res = learner.evaluate(test_fs)
    yield check_results_with_unseen_labels, res, 6, [3, 4, 5]
    yield assert_almost_equal, res[1], 0


# the function to create data with labels that look like floats
# that are either encoded as strings or not depending on the
# keyword argument
def make_float_class_data(labels_as_strings=False):
    """
    We want to create data that has labels that look like
    floats to make sure they are preserved correctly
    """

    ids = ['EXAMPLE_{}'.format(n) for n in range(1, 76)]
    y = [1.2] * 25 + [1.5] * 25 + [1.8] * 25
    if labels_as_strings:
        y = list(map(str, y))
    X = np.vstack([np.identity(25), np.identity(25), np.identity(25)])
    feature_names = ['f{}'.format(i) for i in range(1, 6)]
    features = []
    for row in X:
        features.append(dict(zip(feature_names, row)))

    return FeatureSet('float-classes', ids, features=features, labels=y)


def test_xval_float_classes_as_strings():
    """
    Test that classification with float labels encoded as strings works
    """

    float_class_fs = make_float_class_data(labels_as_strings=True)
    prediction_prefix = join(_my_dir, 'output', 'float_class')
    learner = Learner('LogisticRegression')
    learner.cross_validate(float_class_fs,
                           grid_search=True,
                           grid_objective='accuracy',
                           prediction_prefix=prediction_prefix)

    with open(prediction_prefix + '_predictions.tsv', 'r') as f:
        reader = csv.reader(f, dialect='excel-tab')
        next(reader)
        pred = [row[1] for row in reader]
        for p in pred:
            assert p in ['1.2', '1.5', '1.8']


@raises(ValueError)
def check_bad_xval_float_classes(do_stratified_xval):

    float_class_fs = make_float_class_data()
    prediction_prefix = join(_my_dir, 'output', 'float_class')
    learner = Learner('LogisticRegression')
    learner.cross_validate(float_class_fs,
                           stratified=do_stratified_xval,
                           grid_search=True,
                           grid_objective='accuracy',
                           prediction_prefix=prediction_prefix)


def test_bad_xval_float_classes():

    yield check_bad_xval_float_classes, True
    yield check_bad_xval_float_classes, False


def check_train_and_score_function(model_type):
    """
    Check that the _train_and_score() function works as expected
    """

    # create train and test data
    (train_fs,
     test_fs) = make_classification_data(num_examples=500,
                                         train_test_ratio=0.7,
                                         num_features=5,
                                         use_feature_hashing=False,
                                         non_negative=True)

    # call _train_and_score() on this data
    estimator_name = 'LogisticRegression' if model_type == 'classifier' else 'Ridge'
    metric = 'accuracy' if model_type == 'classifier' else 'pearson'
    learner1 = Learner(estimator_name)
    train_score1, test_score1 = _train_and_score(learner1, train_fs, test_fs, metric)

    # this should yield identical results when training another instance
    # of the same learner without grid search and shuffling and evaluating
    # that instance on the train and the test set
    learner2 = Learner(estimator_name)
    learner2.train(train_fs, grid_search=False, shuffle=False)
    train_score2 = learner2.evaluate(train_fs, output_metrics=[metric])[-1][metric]
    test_score2 = learner2.evaluate(test_fs, output_metrics=[metric])[-1][metric]

    eq_(train_score1, train_score2)
    eq_(test_score1, test_score2)


def test_train_and_score_function():
    yield check_train_and_score_function, 'classifier'
    yield check_train_and_score_function, 'regressor'


@raises(ValueError)
def check_learner_api_grid_search_no_objective(task='train'):

    (train_fs,
     test_fs) = make_classification_data(num_examples=500,
                                         train_test_ratio=0.7,
                                         num_features=5,
                                         use_feature_hashing=False,
                                         non_negative=True)
    learner = Learner('LogisticRegression')
    if task == 'train':
        _ = learner.train(train_fs)
    else:
        _ = learner.cross_validate(train_fs)


def test_learner_api_grid_search_no_objective():
    yield check_learner_api_grid_search_no_objective, 'train'
    yield check_learner_api_grid_search_no_objective, 'cross_validate'


def test_learner_api_load_into_existing_instance():
    """
    Check that `Learner.load()` works as expected
    """

    # create a LinearSVC instance and train it on some data
    learner1 = Learner('LinearSVC')
    (train_fs,
     test_fs) = make_classification_data(num_examples=200,
                                         num_features=5,
                                         use_feature_hashing=False,
                                         non_negative=True)
    learner1.train(train_fs, grid_search=False)

    # now use `load()` to replace the existing instance with a
    # different saved learner
    other_model_file = join(_my_dir, 'other', 'test_load_saved_model.{}.model'.format(sys.version_info[0]))
    learner1.load(other_model_file)

    # now load the saved model into another instance using the class method
    # `from_file()`
    learner2 = Learner.from_file(other_model_file)

    # check that the two instances are now basically the same
    eq_(learner1.model_type, learner2.model_type)
    eq_(learner1.model_params, learner2.model_params)
    eq_(learner1.model_kwargs, learner2.model_kwargs)


@raises(ValueError)
def test_hashing_for_multinomialNB():
    (train_fs, _) = make_classification_data(num_examples=200,
                                             use_feature_hashing=True)
    learner = Learner('MultinomialNB', sampler='RBFSampler')
    learner.train(train_fs, grid_search=False)


@raises(ValueError)
def test_sampling_for_multinomialNB():
    (train_fs, _) = make_classification_data(num_examples=200)
    learner = Learner('MultinomialNB', sampler='RBFSampler')
    learner.train(train_fs, grid_search=False)
