#!/usr/bin/env python
# -*- coding: utf8 -*-

import random
import avoid_tracks

def build_folds(tracks_start_end, piano, orchestra, k_folds=10, temporal_order=20, batch_size=100, long_range_pred=1, random_seed=None, logger_load=None):
    list_files = tracks_start_end.keys()    

    # Folds are built on files, not directly the indices
    # By doing so, we prevent the same file being spread over train, test and validate sets
    random.seed(random_seed)
    random.shuffle(list_files)

    # Remove no validation files
    no_valid_files = set(avoid_tracks.no_valid_tracks())
    list_files_valid = [e for e in list_files if (e not in no_valid_files)]
    list_files_train_only = set(list_files) - set(list_files_valid)

    if k_folds == -1:
        k_folds = len(list_files_valid)

    folds = []
    valid_names = []
    test_names = []
    for k in range(k_folds):
        # For each folds, build list of indices for train, test and validate
        train_ind = []
        valid_ind = []
        valid_ind_long_range = []
        test_ind = []
        this_valid_names = []
        this_test_names = []        
        for counter, filename in enumerate(list_files_valid):
            # Get valid indices for a track
            start_track, end_track = tracks_start_end[filename]
            ind = range(start_track+temporal_order-1, end_track-temporal_order+1)
            ind_long_range = range(start_track+temporal_order-1, end_track-temporal_order-long_range_pred+1)
            counter_fold = counter + k
            if (counter_fold % k_folds) < k_folds-2:
                train_ind.extend(ind)
            elif (counter_fold % k_folds) == k_folds-2:
                this_valid_names.append(filename)
                valid_ind.extend(ind)
                valid_ind_long_range.extend(ind_long_range)
            elif (counter_fold % k_folds) == k_folds-1:
                this_test_names.append(filename)
                test_ind.extend(ind)
        import pdb; pdb.set_trace()
        for filename in list_files_train_only:
            start_track, end_track = tracks_start_end[filename]
            ind = range(start_track+temporal_order-1, end_track-temporal_order+1)
            train_ind.extend(ind)
        train_ind_noSilence = remove_silences(train_ind, piano, orchestra)
        valid_ind_noSilence = remove_silences(valid_ind, piano, orchestra)
        valid_ind_long_range_noSilence = remove_silences(valid_ind_long_range, piano, orchestra)
        test_ind_noSilence = remove_silences(test_ind, piano, orchestra)
        folds.append({'train': build_batches(train_ind_noSilence, batch_size), 
                      'test': build_batches(test_ind_noSilence, batch_size), 
                      'valid': build_batches(valid_ind_noSilence, batch_size),
                      'valid_long_range': build_batches(valid_ind_long_range_noSilence, batch_size)})
        valid_names.append(this_valid_names)
        test_names.append(this_test_names)
    return folds, valid_names, test_names


def build_batches(ind, batch_size):
        batches = []
        position = 0
        n_ind = len(ind)
        
        n_batch = int(n_ind // batch_size)

        # Shuffle indices
        random.shuffle(ind)
       
        for i in range(n_batch):
            batches.append(ind[position:position+batch_size])
            position += batch_size
        # Smaller last batch
        if position < n_ind:
            batches.append(ind[position:n_ind])
        return batches

def remove_silences(indices, piano, orch):
    """ Remove silences from a set of indices. Remove both from piano and orchestra
    
    """
    flat_piano = piano.sum(axis=1)
    flat_orch = orch.sum(axis=1)
    flat_pr = flat_piano * flat_orch
    return [e for e in indices if (flat_pr[e] != 0)]

if __name__ == '__main__':
    build_folds("/Users/leo/Recherche/GitHub_Aciditeam/lop/Data_folds/Data__event_level8")