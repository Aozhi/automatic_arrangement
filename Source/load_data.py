#!/usr/bin/env python
# -*- coding: utf8 -*-

import numpy as np
import theano

import logging
import random
import cPickle as pickle


def load_data(data_folder, set_identifier, temporal_order=20, batch_size=100, generation_length=100,
              binary_unit=True, skip_sample=1,logger_load=None):
    # If no logger, create one
    if logger_load is None:
        logging.basicConfig(level=logging.INFO,
                            format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                            datefmt='%m-%d %H:%M',
                            filename='load.log',
                            filemode='w')
        logger_load=logging.getLogger('load')

    piano = np.load(data_folder + '/piano_' + set_identifier + '.csv')
    orchestra = np.load(data_folder + '/orchestra_' + set_identifier + '.csv')

    # Binary unit ?
    if binary_unit:
        piano[np.nonzero(piano)] = 1
        orchestra[np.nonzero(orchestra)] = 1
    else:
        # Much easier to work with unit between 0 and 1, for several reason :
        #       - 'normalized' values
        #       - same reconstruction as for binary units when building midi files
        piano = piano / 127
        orchestra = orchestra / 127

    # Shared variables : push data on GPU, memory problem for this dataset ??
    # First check type
    type_data = (piano.dtype != theano.config.floatX)
    if type_data:
        logger_load.warning('Incorrect data type for pianorolls')
        logger_load.warning(str(piano.dtype))
    # borrow=True avoid copying the entire matrix
    piano_shared = theano.shared(piano, name='piano_' + set_identifier, borrow=True)
    orchestra_shared = theano.shared(orchestra, name='orchestra_' + set_identifier, borrow=True)

    tracks_start_end = pickle.load(open(data_folder + '/tracks_start_end_' + set_identifier + '.pkl', 'rb'))

    # Get valid indices given start_track and temporal_order
    def valid_indices(tracks_start_end, temporal_order):
        valid_ind = []
        for (start_track, end_track) in tracks_start_end.values():
            valid_ind.extend(range(start_track+temporal_order-1, end_track, skip_sample))
        return valid_ind

    def last_indices(tracks_start_end, temporal_order):
        valid_ind = []
        for (start_track, end_track) in tracks_start_end.values():
            # If the middle of the track is more than temporal_order,
            # Then store it as a generation index
            # if not, take the last index
            # If last index is still not enough, just skip the track
            half_duration = (end_track-start_track) / 2
            middle_track = start_track + half_duration
            if half_duration > temporal_order:
                valid_ind.append(middle_track)
            elif (end_track-start_track) > temporal_order:
                valid_ind.append(end_track-1)
        return valid_ind

    def build_batches(valid_ind):
        batches = []
        position = 0
        n_batch = int(len(valid_ind) // batch_size)

        # Shuffle indices
        random.shuffle(valid_ind)

        for i in range(n_batch):
            batches.append(valid_ind[position:position+batch_size])
            position += batch_size
        return batches

    indices = valid_indices(tracks_start_end, temporal_order)
    batches = build_batches(indices)

    # Generation indices :
    #       For each track :
    #           - middle of track is > temporal_order
    #           - end if not
    #           - nothing if end < temporal_order
    if set_identifier == 'test':
        generation_index = last_indices(tracks_start_end, generation_length)

    if set_identifier != 'test':
        return piano_shared, orchestra_shared, np.asarray(batches, dtype=np.int32)
    else:
        return piano_shared, orchestra_shared, np.asarray(batches, dtype=np.int32), generation_index

# Wrappers
def load_data_train(data_folder, temporal_order=20, batch_size=100, generation_length=100,
                    binary_unit=True, skip_sample=1,logger_load=None):
    return load_data(data_folder, 'train', temporal_order, batch_size, generation_length, binary_unit, skip_sample,logger_load)

def load_data_valid(data_folder, temporal_order=20, batch_size=100, generation_length=100,
                    binary_unit=True, skip_sample=1,logger_load=None):
    return load_data(data_folder, 'valid', temporal_order, batch_size, generation_length, binary_unit, skip_sample,logger_load)

def load_data_test(data_folder, temporal_order=20, batch_size=100, generation_length=100,
                   binary_unit=True, skip_sample=1,logger_load=None):
    return load_data(data_folder, 'test', temporal_order, batch_size, generation_length, binary_unit, skip_sample,logger_load)
