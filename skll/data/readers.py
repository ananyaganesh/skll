# License: BSD 3 clause
"""
This module handles loading data from various types of data files. A
base ``Reader`` class is provided that is sub-classed for each data
file type that is supported, e.g. ``CSVReader``.

Notes about Label Conversion
----------------------------

All ``Reader`` sub-classes use the ``safe_float`` function internally
to read in labels. This function tries to convert a single label
first to ``int``, then to ``float``. If neither conversion is
possible, the label remains a ``str``. It should be noted that, if
classification is being done with a feature set that is read in with
one of the ``Reader`` sub-classes, care must be taken to ensure that
labels do not get converted in unexpected ways. For example,
classification labels should not be a mixture of ``int``-converting
and ``float``-converting labels. Consider the situation below:

>>> import numpy as np
>>> from skll.data.readers import safe_float
>>> np.array([safe_float(x) for x in ["2", "2.2", "2.21"]]) # array([2.  , 2.2 , 2.21])

The labels will all be converted to floats and any classification
model generated with this data will predict labels such as ``2.0``,
``2.2``, etc., not ``str`` values that exactly match the input
labels, as might be expected. Be aware that it may be best to make
use of the ``class_map`` keyword argument in such cases to map
original labels to labels that convert only to ``str``.

:author: Dan Blanchard (dblanchard@ets.org)
:author: Michael Heilman (mheilman@ets.org)
:author: Nitin Madnani (nmadnani@ets.org)
:organization: ETS
"""

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import logging
import re
import sys
from itertools import islice
from io import open, StringIO

import numpy as np
import pandas as pd
from bs4 import UnicodeDammit
from six import PY2, PY3, string_types, text_type
from six.moves import zip
from sklearn.feature_extraction import FeatureHasher

from skll.data import FeatureSet
from skll.data.dict_vectorizer import DictVectorizer


class Reader(object):
    """
    A helper class to make picklable iterators out of example
    dictionary generators.

    Parameters
    ----------
    path_or_list : str or list of dict
        Path or a list of example dictionaries.
    quiet : bool, optional
        Do not print "Loading..." status message to stderr.
        Defaults to ``True``.
    ids_to_floats : bool, optional
        Convert IDs to float to save memory. Will raise error
        if we encounter an a non-numeric ID.
        Defaults to ``False``.
    label_col : str, optional
        Name of the column which contains the class labels
        for ARFF/CSV/TSV files. If no column with that name
        exists, or ``None`` is specified, the data is
        considered to be unlabelled.
        Defaults to ``'y'``.
    id_col : str, optional
        Name of the column which contains the instance IDs.
        If no column with that name exists, or ``None`` is
        specified, example IDs will be automatically generated.
        Defaults to ``'id'``.
    class_map : dict, optional
        Mapping from original class labels to new ones. This is
        mainly used for collapsing multiple labels into a single
        class. Anything not in the mapping will be kept the same.
        Defaults to ``None``.
    sparse : bool, optional
        Whether or not to store the features in a numpy CSR
        matrix when using a DictVectorizer to vectorize the
        features.
        Defaults to ``True``.
    feature_hasher : bool, optional
        Whether or not a FeatureHasher should be used to
        vectorize the features.
        Defaults to ``False``.
    num_features : int, optional
        If using a FeatureHasher, how many features should the
        resulting matrix have?  You should set this to a power
        of 2 greater than the actual number of features to
        avoid collisions.
        Defaults to ``None``.
    logger : logging.Logger, optional
        A logger instance to use to log messages instead of creating
        a new one by default.
        Defaults to ``None``.
    """

    def __init__(self, path_or_list, quiet=True, ids_to_floats=False,
                 label_col='y', id_col='id', class_map=None, sparse=True,
                 feature_hasher=False, num_features=None,
                 logger=None):
        super(Reader, self).__init__()
        self.path_or_list = path_or_list
        self.quiet = quiet
        self.ids_to_floats = ids_to_floats
        self.label_col = label_col
        self.id_col = id_col
        self.class_map = class_map
        self._progress_msg = ''
        self._use_pandas = False

        if feature_hasher:
            self.vectorizer = FeatureHasher(n_features=num_features)
        else:
            self.vectorizer = DictVectorizer(sparse=sparse)
        self.logger = logger if logger else logging.getLogger(__name__)

    @classmethod
    def for_path(cls, path_or_list, **kwargs):
        """
        Instantiate the appropriate Reader sub-class based on the
        file extension of the given path. Or use a dictionary reader
        if the input is a list of dictionaries.

        Parameters
        ----------
        path_or_list : str or list of dicts
            A path or list of example dictionaries.
        kwargs : dict, optional
            The arguments to the Reader object being instantiated.

        Returns
        -------
        reader : skll.Reader
            A new instance of the Reader sub-class that is
            appropriate for the given path.

        Raises
        ------
        ValueError
            If file does not have a valid extension.
        """
        if not isinstance(path_or_list, string_types):
            return DictListReader(path_or_list)
        else:
            # Get lowercase extension for file extension checking
            ext = '.' + path_or_list.rsplit('.', 1)[-1].lower()
            if ext not in EXT_TO_READER:
                raise ValueError(('Example files must be in either .arff, '
                                  '.csv, .jsonlines, .megam, .ndj, or .tsv '
                                  'format. You specified: '
                                  '{}').format(path_or_list))
        return EXT_TO_READER[ext](path_or_list, **kwargs)

    def _sub_read(self, f):
        """
        Does the actual reading of the given file or list.
        For `Reader` objects that do not rely on `pandas`
        (and therefore read row-by-row), this function will
        be called by  `_sub_read_rows()` and will take a file
        buffer rather than a file path. Otherwise, it will
        take a path and will be called directly in the `read()`
        method.

        Parameters
        ----------
        f : file buffer or str
            Either a file buffer, if ``_sub_read_rows()``
            is calling this method, or a path to a file,
            if it is being read with ``pandas``.

        Raises
        ------
        NotImplementedError
        """
        raise NotImplementedError

    def _print_progress(self, progress_num, end="\r"):
        """
        Helper method to print out progress numbers in proper format.
        Nothing gets printed if ``self.quiet`` is ``True``.

        Parameters
        ----------
        progress_num
            Progress indicator value. Usually either a line
            number or a percentage. Must be able to convert to string.

        end : str, optional
            The string to put at the end of the line.  "\\r" should be
            used for every update except for the final one.
            Defaults to ``'\r'``.
        """
        # Print out status
        if not self.quiet:
            print("{}{:>15}".format(self._progress_msg, progress_num),
                  end=end, file=sys.stderr)
            sys.stderr.flush()

    def _sub_read_rows(self, path):
        """
        Read the file in row-by-row. This method is used for
        `Reader` objects that do not rely on `pandas`, and are
        instead read line-by-line into a FeatureSet object, unlike
        pandas-based reader object, which will read everything
        into memory in a data frame object before converting to
        a `FeatureSet`.

        Parameters
        ----------
        path : str
            The path to the file.

        Returns
        -------
        ids : np.array
            The ids array.
        labels : np.array
            The labels array.
        features : list of dicts
            The features dictionary.

        Raises
        ------
        ValueError
            If ``ids_to_floats`` is True, but IDs cannot be converted.
        ValueError
            If no features are found.
        ValueError
            If the example IDs are not unique.
        """
        # Get labels and IDs
        ids = []
        labels = []
        ex_num = 0
        with open(path, 'r' if PY3 else 'rb') as f:
            for ex_num, (id_, class_, _) in enumerate(self._sub_read(f), start=1):

                # Update lists of IDs, classes, and features
                if self.ids_to_floats:
                    try:
                        id_ = float(id_)
                    except ValueError:
                        raise ValueError(('You set ids_to_floats to true,'
                                          ' but ID {} could not be '
                                          'converted to float in '
                                          '{}').format(id_,
                                                       self.path_or_list))
                ids.append(id_)
                labels.append(class_)
                if ex_num % 100 == 0:
                    self._print_progress(ex_num)
            self._print_progress(ex_num)

        # Remember total number of examples for percentage progress meter
        total = ex_num
        if total == 0:
            raise ValueError("No features found in possibly "
                             "empty file '{}'.".format(self.path_or_list))

        # Convert everything to numpy arrays
        ids = np.array(ids)
        labels = np.array(labels)

        def feat_dict_generator():
            with open(self.path_or_list, 'r' if PY3 else 'rb') as f:
                for ex_num, (_, _, feat_dict) in enumerate(self._sub_read(f)):
                    yield feat_dict
                    if ex_num % 100 == 0:
                        self._print_progress('{:.8}%'.format(100 * ((ex_num / total))))
                self._print_progress("100%")

        # extract the features dictionary
        features = feat_dict_generator()

        return ids, labels, features

    def _parse_dataframe(self, df, id_col, label_col, features=None):
        """
        Parse the data frame into ids, labels, and features.
        For `Reader` objects that rely on `pandas`, this function
        will be called in the `_sub_read()` method to parse the
        data frame into the expected format. It will not be used
        by `Reader` classes that read row-by-row (and therefore
        use the `_sub_read_rows()` function).

        Parameters
        ----------
        df : pd.DataFrame
            The pandas data frame to parse.
        id_col : str or None
            The id column.
        label_col : str or None
            The label column.
        features : list of dict or None
            The features, if they already exist;
            if not, then they will be extracted
            from the data frame.
            Defaults to None.

        Returns
        -------
        ids : np.array
            The ids for the feature set.
        labels : np.array
            The labels for the feature set.
        features : list of dicts
            The features for the feature set.
        """
        if df.empty:
            raise ValueError("No features found in possibly "
                             "empty file '{}'.".format(self.path_or_list))

        # if the id column exists,
        # get them from the data frame and
        # delete the column; otherwise, just
        # set it to None
        if id_col is not None and id_col in df:
            ids = df[id_col]
            del df[id_col]
            # if `ids_to_floats` is True,
            # then convert the ids to floats
            if self.ids_to_floats:
                ids = ids.astype(float)
            ids = ids.values
        else:
            # create ids with the prefix `EXAMPLE_`
            ids = np.array(['EXAMPLE_{}'.format(i) for i in range(df.shape[0])])

        # if the label column exists,
        # get them from the data frame and
        # delete the column; otherwise, just
        # set it to None
        if label_col is not None and label_col in df:
            labels = df[label_col]
            del df[label_col]
            # if `class_map` exists, then
            # map the new classes to the labels;
            # otherwise, just convert them to floats
            if self.class_map is not None:
                labels = labels.apply(safe_float,
                                      replace_dict=self.class_map)
            else:
                labels = labels.apply(safe_float)
            labels = labels.values
        else:
            # create an array of Nones
            labels = np.array([None] * df.shape[0])

        # convert the remaining features to
        # a list of dictionaries, if no
        # features argument was passed
        if features is None:
            features = df.to_dict(orient='records')

        return ids, labels, features

    def read(self):
        """
        Loads examples in the `.arff`, `.csv`, `.jsonlines`, `.libsvm`,
        `.megam`, `.ndj`, or `.tsv` formats.

        Returns
        -------
        feature_set : skll.FeatureSet
            ``FeatureSet`` instance representing the input file.

        Raises
        ------
        ValueError
            If ``ids_to_floats`` is True, but IDs cannot be converted.
        ValueError
            If no features are found.
        ValueError
            If the example IDs are not unique.
        """
        self.logger.debug('Path: %s', self.path_or_list)

        if not self.quiet:
            self._progress_msg = "Loading {}...".format(self.path_or_list)
            print(self._progress_msg, end="\r", file=sys.stderr)
            sys.stderr.flush()

        if self._use_pandas:
            ids, labels, features = self._sub_read(self.path_or_list)
        else:
            ids, labels, features = self._sub_read_rows(self.path_or_list)

        # Convert everything to numpy arrays
        features = self.vectorizer.fit_transform(features)

        # Report that loading is complete
        self._print_progress("done", end="\n")

        # Make sure we have the same number of ids, labels, and features
        assert ids.shape[0] == labels.shape[0] == features.shape[0]

        if ids.shape[0] != len(set(ids)):
            raise ValueError('The example IDs are not unique in %s.' %
                             self.path_or_list)

        return FeatureSet(self.path_or_list, ids, labels=labels,
                          features=features, vectorizer=self.vectorizer)


class DictListReader(Reader):
    """
    This class is to facilitate programmatic use of
    ``Learner.predict()`` and other methods that take
    ``FeatureSet`` objects as input. It iterates
    over examples in the same way as other ``Reader`` classes, but uses a
    list of example dictionaries instead of a path to a file.

    Parameters
    ----------
    path_or_list : str
        The path to a comma-delimited file.
    pandas_kwargs : dict or None, optional
        Arguments that will be passed directly
        to the `pandas` data frame constructor.
        Defaults to None.
    kwargs : dict, optional
        Other arguments to the Reader object.
    """

    def __init__(self, path_or_list, pandas_kwargs=None, **kwargs):
        super(DictListReader, self).__init__(path_or_list, **kwargs)
        self._pandas_kwargs = {} if pandas_kwargs is None else pandas_kwargs
        self._use_pandas = True

    def _sub_read(self, list_of_dicts):
        """
        The function called to create the feature set
        from a list of dictionaries

        Parameters
        ----------
        list_of_dicts : list of dicts
            A list of dictionaries in DictList
            format.
        """

        # create a data frame; if it's empty,
        # then return `_parse_dataframe()`, which
        # will raise an error
        df = pd.DataFrame(list_of_dicts, **self._pandas_kwargs)
        if df.empty:
            return self._parse_dataframe(df, None, None)

        # if it's PY2 and `id` is in the
        # data frame, make sure it's a string
        if PY2 and 'id' in df:
            df['id'] = df['id'].astype(str)

        # convert the features to a
        # list of dictionaries
        features = df['x'].tolist()
        return self._parse_dataframe(df,
                                     'id' if 'id' in df else None,
                                     'y' if 'y' in df else None,
                                     features=features)


class NDJReader(Reader):

    """
    Reader to create a ``FeatureSet`` instance from a JSONlines/NDJ file.

    If example/instance IDs are included in the files, they
    must be specified as the  "id" key in each JSON dictionary.

    Parameters
    ----------
    path_or_list : str
        The path to a comma-delimited file.
    pandas_kwargs : dict or None, optional
        Arguments that will be passed directly
        to the `pandas` I/O reader.
        Defaults to None.
    kwargs : dict, optional
        Other arguments to the Reader object.
    """

    def __init__(self, path_or_list, pandas_kwargs=None, **kwargs):
        super(NDJReader, self).__init__(path_or_list, **kwargs)
        self._pandas_kwargs = {} if pandas_kwargs is None else pandas_kwargs
        # remove the `lines` and `orient` arguments, if they were passed
        self._pandas_kwargs.pop('lines', None)
        self._pandas_kwargs.pop('orient', None)
        self._use_pandas = True

    def _sub_read(self, path):
        """
        The function called on the file buffer in the ``read()`` method
        to iterate through rows.

        Parameters
        ----------
        path : str
            The path to the NDJ file.

        Returns
        -------
        ids : np.array
            The ids for the feature set.
        labels : np.array
            The labels for the feature set.
        features : list of dicts
            The features for the features set.
        """
        # create a data frame; if it's empty,
        # then return `_parse_dataframe()`, which
        # will raise an error
        df = pd.read_json(path, orient='records', lines=True, **self._pandas_kwargs)
        if df.empty:
            return self._parse_dataframe(df, None, None)

        # if `id` is in the data frame, make sure it's a string
        if 'id' in df:
            df['id'] = df['id'].astype(str)

        # convert the features to a
        # list of dictionaries
        features = df['x'].tolist()
        return self._parse_dataframe(df,
                                     'id' if 'id' in df else None,
                                     'y' if 'y' in df else None,
                                     features=features)


class MegaMReader(Reader):

    """
    Reader to create a ``FeatureSet`` instance from  a MegaM -fvals file.

    If example/instance IDs are included in the files, they must be specified
    as a comment line directly preceding the line with feature values.
    """

    def _sub_read(self, f):
        """
        Parameters
        ----------
        f : file buffer
            A file buffer for an MegaM file.

        Yields
        ------
        curr_id : str
            The current ID for the example.
        class_name : float or str
            The name of the class label for the example.
        example : dict
            The example valued in dictionary format, with 'x'
            as list of features.

        Raises
        ------
        ValueError
            If there are duplicate feature names.
        """
        example_num = 0
        curr_id = 'EXAMPLE_0'
        for line in f:
            # Process encoding
            if not isinstance(line, text_type):
                line = UnicodeDammit(line, ['utf-8',
                                            'windows-1252']).unicode_markup
            line = line.strip()
            # Handle instance lines
            if line.startswith('#'):
                curr_id = line[1:].strip()
            elif line and line not in ['TRAIN', 'TEST', 'DEV']:
                split_line = line.split()
                num_cols = len(split_line)
                del line
                # Line is just a class label
                if num_cols == 1:
                    class_name = safe_float(split_line[0],
                                            replace_dict=self.class_map)
                    field_pairs = []
                # Line has a class label and feature-value pairs
                elif num_cols % 2 == 1:
                    class_name = safe_float(split_line[0],
                                            replace_dict=self.class_map)
                    field_pairs = split_line[1:]
                # Line just has feature-value pairs
                elif num_cols % 2 == 0:
                    class_name = None
                    field_pairs = split_line

                curr_info_dict = {}
                if len(field_pairs) > 0:
                    # Get current instances feature-value pairs
                    field_names = islice(field_pairs, 0, None, 2)
                    # Convert values to floats, because otherwise
                    # features'll be categorical
                    field_values = (safe_float(val) for val in
                                    islice(field_pairs, 1, None, 2))

                    # Add the feature-value pairs to dictionary
                    curr_info_dict.update(zip(field_names, field_values))

                    if len(curr_info_dict) != len(field_pairs) / 2:
                        raise ValueError(('There are duplicate feature ' +
                                          'names in {} for example ' +
                                          '{}.').format(self.path_or_list,
                                                        curr_id))

                yield curr_id, class_name, curr_info_dict

                # Set default example ID for next instance, in case we see a
                # line without an ID.
                example_num += 1
                curr_id = 'EXAMPLE_{}'.format(example_num)


class LibSVMReader(Reader):

    """
    Reader to create a ``FeatureSet`` instance from a LibSVM/LibLinear/SVMLight file.

    We use a specially formatted comment for storing example IDs, class names,
    and feature names, which are normally not supported by the format.  The
    comment is not mandatory, but without it, your labels and features will
    not have names.  The comment is structured as follows::

        ExampleID | 1=FirstClass | 1=FirstFeature 2=SecondFeature
    """

    line_regex = re.compile(r'^(?P<label_num>[^ ]+)\s+(?P<features>[^#]*)\s*'
                            r'(?P<comments>#\s*(?P<example_id>[^|]+)\s*\|\s*'
                            r'(?P<label_map>[^|]+)\s*\|\s*'
                            r'(?P<feat_map>.*)\s*)?$', flags=re.UNICODE)

    LIBSVM_REPLACE_DICT = {'\u2236': ':',
                           '\uFF03': '#',
                           '\u2002': ' ',
                           '\ua78a': '=',
                           '\u2223': '|'}

    @staticmethod
    def _pair_to_tuple(pair, feat_map):
        """
        Split a feature-value pair separated by a colon into a tuple.  Also
        do safe_float conversion on the value.

        Parameters
        ----------
        feat_map : str
            A feature-value pair to split.

        Returns
        -------
        name : str
            The name of the feature.
        value
            The value of the example.
        """
        name, value = pair.split(':')
        if feat_map is not None:
            name = feat_map[name]
        value = safe_float(value)
        return (name, value)

    def _sub_read(self, f):
        """
        Parameters
        ----------
        f : file buffer
            A file buffer for an LibSVM file.

        Yields
        ------
        curr_id : str
            The current ID for the example.
        class_name : float or str
            The name of the class label for the example.
        example : dict
            The example valued in dictionary format, with 'x'
            as list of features.

        Raises
        ------
        ValueError
            If line does not look like valid libsvm format.
        """
        for example_num, line in enumerate(f):
            curr_id = ''
            # Decode line if it's not already str
            if isinstance(line, bytes):
                line = UnicodeDammit(line, ['utf-8',
                                            'windows-1252']).unicode_markup
            match = self.line_regex.search(line.strip())
            if not match:
                raise ValueError('Line does not look like valid libsvm format'
                                 '\n{}'.format(line))
            # Metadata is stored in comments if this was produced by SKLL
            if match.group('comments') is not None:
                # Store mapping from feature numbers to names
                if match.group('feat_map'):
                    feat_map = {}
                    for pair in match.group('feat_map').split():
                        number, name = pair.split('=')
                        for orig, replacement in \
                                LibSVMReader.LIBSVM_REPLACE_DICT.items():
                            name = name.replace(orig, replacement)
                        feat_map[number] = name
                else:
                    feat_map = None
                # Store mapping from label/class numbers to names
                if match.group('label_map'):
                    label_map = dict(pair.split('=') for pair in
                                     match.group('label_map').strip().split())
                else:
                    label_map = None
                curr_id = match.group('example_id').strip()

            if not curr_id:
                curr_id = 'EXAMPLE_{}'.format(example_num)

            class_num = match.group('label_num')
            # If we have a mapping from class numbers to labels, get label
            if label_map:
                class_name = label_map[class_num]
            else:
                class_name = class_num
            class_name = safe_float(class_name,
                                    replace_dict=self.class_map)

            curr_info_dict = dict(self._pair_to_tuple(pair, feat_map) for pair
                                  in match.group('features').strip().split())

            yield curr_id, class_name, curr_info_dict


class CSVReader(Reader):

    """
    Reader for creating a ``FeatureSet`` instance from a CSV file.

    If example/instance IDs are included in the files, they
    must be specified in the ``id`` column.

    Also, there must be a column with the name specified by ``label_col`` if the
    data is labeled.

    Parameters
    ----------
    path_or_list : str
        The path to a comma-delimited file.
    pandas_kwargs : dict or None, optional
        Arguments that will be passed directly
        to the `pandas` I/O reader.
        Defaults to None.
    kwargs : dict, optional
        Other arguments to the Reader object.
    """

    def __init__(self, path_or_list, pandas_kwargs=None, **kwargs):
        super(CSVReader, self).__init__(path_or_list, **kwargs)
        self._pandas_kwargs = {} if pandas_kwargs is None else pandas_kwargs
        self._sep = self._pandas_kwargs.pop('sep', str(','))
        self._engine = self._pandas_kwargs.pop('engine', 'c')
        self._use_pandas = True

    def _sub_read(self, path):
        """
        Parameters
        ----------
        path : str
            The path to the CSV file.

        Returns
        -------
        ids : np.array
            The ids for the feature set.
        labels : np.array
            The labels for the feature set.
        features : list of dicts
            The features for the features set.
        """
        df = pd.read_csv(path, sep=self._sep, engine=self._engine, **self._pandas_kwargs)
        return self._parse_dataframe(df, self.id_col, self.label_col)


class TSVReader(CSVReader):

    """
    Reader for creating a ``FeatureSet`` instance from a TSV file.

    If example/instance IDs are included in the files, they
    must be specified in the ``id`` column.

    Also there must be a column with the name specified by ``label_col``
    if the data is labeled.

    Parameters
    ----------
    path_or_list : str
        The path to a comma-delimited file.
    pandas_kwargs : dict or None, optional
        Arguments that will be passed directly
        to the `pandas` I/O reader.
        Defaults to None.
    kwargs : dict, optional
        Other arguments to the Reader object.
    """

    def __init__(self, path_or_list, pandas_kwargs=None, **kwargs):
        super(TSVReader, self).__init__(path_or_list, pandas_kwargs, **kwargs)
        self._sep = str('\t')


class ARFFReader(Reader):

    """
    Reader for creating a ``FeatureSet`` instance from an ARFF file.

    If example/instance IDs are included in the files, they
    must be specified in the ``id`` column.

    Also, there must be a column with the name specified by ``label_col`` if the
    data is labeled, and this column must be the final one (as it is in Weka).

    Parameters
    ----------
    path_or_list : str
        The path to a comma-delimited file.
    pandas_kwargs : dict or None, optional
        Arguments that will be passed directly
        to the `pandas` I/O reader.
        Defaults to None.
    kwargs : dict, optional
        Other arguments to the Reader object.
    """

    def __init__(self, path_or_list, pandas_kwargs=None, **kwargs):
        super(ARFFReader, self).__init__(path_or_list, **kwargs)
        self.dialect = 'arff'
        self.relation = ''
        self.regression = False
        self._pandas_kwargs = {} if pandas_kwargs is None else pandas_kwargs
        self._engine = self._pandas_kwargs.pop('engine', 'c')
        # remove all the things that the user isn't allowed to set
        self._pandas_kwargs.pop('delimiter', None)
        self._pandas_kwargs.pop('header', None)
        self._pandas_kwargs.pop('quote_char', None)
        self._pandas_kwargs.pop('escape_char', None)
        self._use_pandas = True

    def split_with_quotes(self,
                          s,
                          delimiter=' ',
                          header=None,
                          quote_char="'",
                          escape_char='\\'):
        """
        A replacement for string.split that won't split delimiters enclosed in
        quotes.

        Parameters
        ----------
        s : str
            The string with quotes to split
        header : list or None, optional
            The names of the header columns
            or None.
            Defaults to ``None``.
        delimiter : str, optional
            The delimiter to split on.
            Defaults to ``' '``.
        quote_char : str, optional
            The quote character to ignore.
            Defaults to ``"'"``.
        escape_char : str, optional
            The escape character.
            Defaults to ``'\\'``.
        """
        if PY2:
            delimiter = delimiter.encode()
            quote_char = quote_char.encode()
            escape_char = escape_char.encode()

        # additional arguments we want
        # to pass to the `pd.read_csv()` function
        kwargs = {'header': header,
                  'delimiter': delimiter,
                  'quotechar': quote_char,
                  'escapechar': escape_char}
        kwargs.update(self._pandas_kwargs)

        df = pd.read_csv(StringIO(s), engine=self._engine, **kwargs)
        return df

    def _sub_read(self, path):
        """
        Parameters
        ----------
        path : str
            The path to the ARFF file.

        Returns
        -------
        ids : np.array
            The ids for the feature set.
        labels : np.array
            The labels for the feature set.
        features : list of dicts
            The features for the features set.
        """
        with open(path, 'r' if PY3 else 'rb') as buff:

            lines = [UnicodeDammit(line.strip(), ['utf-8', 'windows-1252']).unicode_markup
                     if not isinstance(line, text_type) and PY2
                     else line.strip()
                     for line in buff if line.strip()]

        # find the row index starting with data; the line below this
        # is where the data should actually begin
        data_idx = lines.index('@data')

        df = self.split_with_quotes('\n'.join(lines[data_idx + 1:]), delimiter=',')

        # get the column names from the attribute
        # rows, and add them to the columns list
        columns = []
        for row in lines[:data_idx]:

            row_series = self.split_with_quotes(row)
            if row_series.loc[0, 0] == '@attribute':
                column = row_series.loc[0, 1]
                columns.append(column)

                # if the column is the label column,
                # and the type is 'numeric', set regression
                # to True; otherwise False
                if column == self.label_col:
                    self.regression = row_series.loc[0, 2] == 'numeric'

            # if the relation attribute exists, then
            # add it to the relation instance variable
            elif row_series.loc[0, 0] == '@relation':
                self.relation = row_series.loc[0, 1]

        df.columns = columns
        return self._parse_dataframe(df, self.id_col, self.label_col)


def safe_float(text, replace_dict=None, logger=None):
    """
    Attempts to convert a string to an int, and then a float, but if neither is
    possible, returns the original string value.

    Parameters
    ----------
    text : str
        The text to convert.
    replace_dict : dict, optional
        Mapping from text to replacement text values. This is
        mainly used for collapsing multiple labels into a
        single class. Replacing happens before conversion to
        floats. Anything not in the mapping will be kept the
        same.
        Defaults to ``None``.
    logger : logging.Logger
        The Logger instance to use to log messages. Used instead of
        creating a new Logger instance by default.
        Defaults to ``None``.

    Returns
    -------
    text : int or float or str
        The text value converted to int or float, if possible
    """

    # convert to text to be "Safe"!
    text = text_type(text)

    # get a logger unless we are passed one
    if not logger:
        logger = logging.getLogger(__name__)

    if replace_dict is not None:
        if text in replace_dict:
            text = replace_dict[text]
        else:
            logger.warning('Encountered value that was not in replacement '
                           'dictionary (e.g., class_map): {}'.format(text))
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text.decode('utf-8') if PY2 else text
        except TypeError:
            return 0.0
    except TypeError:
        return 0


# Constants
EXT_TO_READER = {".arff": ARFFReader,
                 ".csv": CSVReader,
                 ".jsonlines": NDJReader,
                 ".libsvm": LibSVMReader,
                 ".megam": MegaMReader,
                 '.ndj': NDJReader,
                 ".tsv": TSVReader}
