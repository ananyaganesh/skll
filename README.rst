SciKit-Learn Laboratory
-----------------------

.. image:: https://img.shields.io/travis/EducationalTestingService/skll/master.svg
   :alt: Build status
   :target: https://travis-ci.org/EducationalTestingService/skll

.. image:: https://img.shields.io/coveralls/EducationalTestingService/skll/master.svg
    :target: https://coveralls.io/r/EducationalTestingService/skll

.. image:: https://img.shields.io/pypi/v/skll.svg
   :target: https://pypi.org/project/skll/
   :alt: Latest version on PyPI

.. image:: https://img.shields.io/pypi/l/skll.svg
   :alt: License

.. image:: https://img.shields.io/conda/v/desilinguist/skll.svg
   :target: https://anaconda.org/desilinguist/skll
   :alt: Conda package for SKLL

.. image:: https://img.shields.io/pypi/pyversions/skll.svg
   :target: https://pypi.org/project/skll/
   :alt: Supported python versions for SKLL

.. image:: https://img.shields.io/badge/DOI-10.5281%2Fzenodo.12825-blue.svg
   :target: http://dx.doi.org/10.5281/zenodo.12825
   :alt: DOI for citing SKLL 1.0.0

This Python package provides command-line utilities to make it easier to run
machine learning experiments with scikit-learn.  One of the primary goals of
our project is to make it so that you can run scikit-learn experiments without
actually needing to write any code other than what you used to generate/extract
the features.

Command-line Interface
~~~~~~~~~~~~~~~~~~~~~~

The main utility we provide is called ``run_experiment`` and it can be used to
easily run a series of learners on datasets specified in a configuration file
like:

.. code:: ini

  [General]
  experiment_name = Titanic_Evaluate_Tuned
  # valid tasks: cross_validate, evaluate, predict, train
  task = evaluate

  [Input]
  # these directories could also be absolute paths
  # (and must be if you're not running things in local mode)
  train_directory = train
  test_directory = dev
  # Can specify multiple sets of feature files that are merged together automatically
  # (even across formats)
  featuresets = [["family.ndj", "misc.csv", "socioeconomic.arff", "vitals.csv"]]
  # List of scikit-learn learners to use
  learners = ["RandomForestClassifier", "DecisionTreeClassifier", "SVC", "MultinomialNB"]
  # Column in CSV containing labels to predict
  label_col = Survived
  # Column in CSV containing instance IDs (if any)
  id_col = PassengerId

  [Tuning]
  # Should we tune parameters of all learners by searching provided parameter grids?
  grid_search = true
  # Function to maximize when performing grid search
  objectives = ['accuracy']

  [Output]
  # Also compute the area under the ROC curve as an additional metric
  metrics = ['roc_auc']
  # The following can/should be absolute paths
  log = output
  results = output
  predictions = output
  models = output


For more information about getting started with ``run_experiment``, please check
out `our tutorial <https://skll.readthedocs.org/en/latest/tutorial.html>`__, or
`our config file specs <https://skll.readthedocs.org/en/latest/run_experiment.html>`__.

We also provide utilities for:

-  `converting between machine learning toolkit formats <https://skll.readthedocs.org/en/latest/utilities.html#skll-convert>`__
   (e.g., ARFF, CSV, MegaM)
-  `filtering feature files <https://skll.readthedocs.org/en/latest/utilities.html#filter-features>`__
-  `joining feature files <https://skll.readthedocs.org/en/latest/utilities.html#join-features>`__
-  `other common tasks <https://skll.readthedocs.org/en/latest/utilities.html>`__


Python API
~~~~~~~~~~

If you just want to avoid writing a lot of boilerplate learning code, you can
also use our simple Python API which also supports pandas DataFrames.
The main way you'll want to use the API is through
the ``Learner`` and ``Reader`` classes. For more details on our API, see
`the documentation <https://skll.readthedocs.org/en/latest/api.html>`__.

While our API can be broadly useful, it should be noted that the command-line
utilities are intended as the primary way of using SKLL.  The API is just a nice
side-effect of our developing the utilities.


A Note on Pronunciation
~~~~~~~~~~~~~~~~~~~~~~~

.. image:: doc/skll.png
   :alt: SKLL logo
   :align: right

.. container:: clear

  .. image:: doc/spacer.png

SciKit-Learn Laboratory (SKLL) is pronounced "skull": that's where the learning
happens.

Requirements
~~~~~~~~~~~~

-  Python 2.7+
-  `scikit-learn <http://scikit-learn.org/stable/>`__
-  `six <https://pypi.org/project/six/>`__
-  `tabulate <https://pypi.org/project/tabulate/>`__
-  `BeautifulSoup 4 <http://www.crummy.com/software/BeautifulSoup/>`__
-  `pandas <http://pandas.pydata.org>`__
-  `Grid Map <https://pypi.org/project/gridmap/>`__ (only required if you plan
   to run things in parallel on a DRMAA-compatible cluster)
-  `joblib <https://pypi.org/project/joblib/>`__
-  `ruamel.yaml <http://yaml.readthedocs.io/en/latest/overview.html>`__
-  `configparser <https://pypi.org/project/configparser/>`__ (only required for
   Python 2.7)
-  `logutils <https://pypi.org/project/logutils/>`__ (only required for Python 2.7)
-  `mock <https://pypi.org/project/mock/>`__ (only required for Python 2.7)

The following packages can be optionally installed for additional features
but are not required:

-  `seaborn <http://seaborn.pydata.org>`__ (optional)

Talks
~~~~~

-  *Simpler Machine Learning with SKLL 1.0*, Dan Blanchard, PyData NYC 2014 (`video <https://www.youtube.com/watch?v=VEo2shBuOrc&feature=youtu.be&t=1s>`__ | `slides <http://www.slideshare.net/DanielBlanchard2/py-data-nyc-2014>`__)
-  *Simpler Machine Learning with SKLL*, Dan Blanchard, PyData NYC 2013 (`video <http://vimeo.com/79511496>`__ | `slides <http://www.slideshare.net/DanielBlanchard2/simple-machine-learning-with-skll>`__)

Books
~~~~~

SKLL is featured in `Data Science at the Command Line <http://datascienceatthecommandline.com>`__
by `Jeroen Janssens <http://jeroenjanssens.com>`__.

Changelog
~~~~~~~~~

See `GitHub releases <https://github.com/EducationalTestingService/skll/releases>`__.
