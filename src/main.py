import random
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow import keras

from predict.api import generate_complete_beatmaps
from process.api import create_song_list, songs2dataset
from train.callbacks import create_callbacks
from train.model import create_model
from train.sequence import BeatmapSequence
from utils.functions import check_consistency
from utils.types import Config, Timer


def generate_datasets(config: Config):
    timer = Timer()
    for phase, split in zip(['train', 'val', 'test'],
                            zip(config.training['data_split'],
                                config.training['data_split'][1:])
                            ):
        print('\n', '=' * 100, sep='')
        print(f'Processing {phase}')
        split_from = int(total * split[0])
        split_to = int(total * split[1])
        result_path = config.dataset['storage_folder'] / f'{phase}_beatmaps.pkl'

        df = songs2dataset(song_folders[split_from:split_to], config=config)
        timer(f'Created {phase} dataset', 1)

        check_consistency(df)

        config.dataset['storage_folder'].mkdir(parents=True, exist_ok=True)
        df.to_pickle(result_path)
        timer(f'Pickled {phase} dataset', 1)


def load_datasets(config: Config) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return [pd.read_pickle(config.dataset['storage_folder'] / f'{phase}_beatmaps.pkl') for phase in
            ['train', 'val', 'test']]


def dataset_stats(df: pd.DataFrame):
    print(df)
    group_over = ['name', 'difficulty', 'snippet', 'time', ]
    for end_index in range(1, len(group_over) + 1):
        print(f"{df.groupby(group_over[:end_index]).ngroups:9} {' × '.join(group_over[:end_index])}")


def list2numpy(batch, col_name, groupby=('name')):
    return np.array(batch.groupby(list(groupby))[col_name].apply(list).to_list())


def create_training_data(X, groupby, config: Config):
    X_cols = config.dataset['audio']
    y_cols = config.dataset['beat_elements']
    return [list2numpy(X, col, groupby) for col in X_cols], \
           [list2numpy(X, col, groupby) for col in y_cols]


def main():
    tf.random.set_seed(43)
    np.random.seed(43)
    random.seed(43)

    base_folder = Path('../data')
    song_folders = create_song_list(base_folder)
    total = len(song_folders)
    print(f'Found {total} folders')
    #
    config = Config()
    config.dataset['storage_folder'] = base_folder / 'full_datasets'
    config.dataset['storage_folder'] = base_folder / 'new_datasets'
    # config.audio_processing['use_cache'] = False

    # generate_datasets(config)

    train, val, test = load_datasets(config)
    train.drop(index='133b', inplace=True)
    dataset_stats(train)

    train_seq = BeatmapSequence(train, config)
    val_seq = BeatmapSequence(val, config)
    test_seq = BeatmapSequence(test, config)

    print(train.reset_index('name')['name'].unique())

    keras.mixed_precision.experimental.set_policy('mixed_float16')
    model_path = base_folder / 'temp'
    model_path.mkdir(parents=True, exist_ok=True)

    train = True
    train = False
    if train:
        model = create_model(train_seq, False, config)
        model.summary()

        callbacks = create_callbacks(train_seq, config)

        timer = Timer()

        model.fit(train_seq,
                  validation_data=val_seq,
                  callbacks=callbacks,
                  epochs=100,
                  verbose=2)
        timer('Training ')

        save_model(model, model_path, train_seq, config)

    stateful_model = keras.models.load_model(model_path / 'stateful_model.keras')
    print('Evaluation')

    # gen_new_beat_map_path = song_folders[-2]
    # gen_new_beat_map_path = Path('../data/new_dataformat/4ede/')
    # beatmap_folder = base_folder / 'testing/generation/'
    # beatmap_folder = base_folder / 'testing' / 'truncated_song'
    # beatmap_folder = base_folder / 'testing/generation_normal/'
    # beatmap_folder = base_folder / 'new_dataformat' / '3205'
    beatmap_folder = base_folder / 'new_dataformat' / '133b'

    output_folder = base_folder / 'testing' / 'generated_songs'

    generate_complete_beatmaps(beatmap_folder, output_folder, stateful_model, config)


def save_model(model, model_path, train_seq, config):
    keras.mixed_precision.experimental.set_policy('float32')
    config.training['batch_size'] = 1
    stateful_model = create_model(train_seq, True, config)
    stateful_model.set_weights(model.get_weights())
    model.save(model_path / 'model.keras')
    stateful_model.save(model_path / 'stateful_model.keras')
    return stateful_model


if __name__ == '__main__':
    main()