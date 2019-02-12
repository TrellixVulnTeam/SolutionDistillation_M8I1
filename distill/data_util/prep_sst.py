import tensorflow as tf
import os
import itertools
from collections import OrderedDict
from tqdm import tqdm
from distill.data_util.trees import Tree, leftTraverse
from distill.data_util.vocab import Vocab


class SST(object):
  def __init__(self, data_path):
    self.data_path = data_path

    self.vocab_path = os.path.join(data_path, "vocab")
    self.vocab = Vocab(path=self.vocab_path)
    self.load_vocab()

  def load_vocab(self):
    if self.vocab.exists():
      self.vocab.load()
    else:
      self.load_data()

      # Get list of tokenized sentences
      train_sents = [t.get_words() for t in self.data["train"]]
      # Get list of all words
      all_words = list(itertools.chain.from_iterable(train_sents))
      self.vocab.build_vocab(all_words)
      self.vocab.save()

  def get_examples(self, mode):
    example_features = []
    for example_id, tree in enumerate(self.data[mode]):
      words = tree.get_words()
      node = tree.root
      nodes_list = []
      leftTraverse(node, lambda node, args: args.append(node), nodes_list)
      node_to_index = OrderedDict()
      for i in range(len(nodes_list)):
        node_to_index[nodes_list[i]] = i
      example_features.append({
        'example_id': example_id,
        'is_leaf': [int(node.isLeaf) for node in nodes_list],
        'left_children': [0] + [node_to_index[node.left]+1 if
                          not node.isLeaf else 0
                          for node in nodes_list],
        'right_children': [0] + [node_to_index[node.right]+1 if
                           not node.isLeaf else 0
                           for node in nodes_list],
        'node_word_ids': [0] + [self.vocab.encode(node.word)[0] if
                          node.word else 0
                          for node in nodes_list],
        'labels': [node.label for node in nodes_list],
        'binary_labels': [0 if node.label <= 2 else 1 for node in nodes_list],
        'length': len(nodes_list),
        'word_length': len(words),
        'word_ids': [self.vocab.encode(word)[0] for word in words],
        'root_label': [tree.root.label],
        'root_binary_label': [0 if tree.root.label <= 2 else 1]
      })

    return example_features

  def get_all_tf_features(self, example_feaures):
    """Convert our own representation of an example's features to Features class for TensorFlow dataset.
    """
    features = tf.train.Features(feature={
      "example_id": tf.train.Feature(int64_list=tf.train.Int64List(value=[example_feaures['example_id']])),
      "is_leaf": tf.train.Feature(int64_list=tf.train.Int64List(value=example_feaures['is_leaf'])),
      "left_children": tf.train.Feature(int64_list=tf.train.Int64List(value=example_feaures['left_children'])),
      "right_children": tf.train.Feature(int64_list=tf.train.Int64List(value=example_feaures['right_children'])),
      "node_word_ids": tf.train.Feature(int64_list=tf.train.Int64List(value=example_feaures['node_word_ids'])),
      "labels": tf.train.Feature(int64_list=tf.train.Int64List(value=example_feaures['labels'])),
      "binary_labels": tf.train.Feature(int64_list=tf.train.Int64List(value=example_feaures['binary_labels'])),
      "length": tf.train.Feature(int64_list=tf.train.Int64List(value=[example_feaures['length']])),
      "root_label": tf.train.Feature(int64_list=tf.train.Int64List(value=example_feaures['root_label'])),
      "root_binary_label": tf.train.Feature(int64_list=tf.train.Int64List(value=example_feaures['root_binary_label'])),
      "word_length": tf.train.Feature(int64_list=tf.train.Int64List(value=[example_feaures['word_length']])),
      "word_ids": tf.train.Feature(int64_list=tf.train.Int64List(value=example_feaures['word_ids'])),

    })
    return features



  def get_plain_tf_features(self, example_feaures):
    """Convert our own representation of an example's features to Features class for TensorFlow dataset.
    """
    features = tf.train.Features(feature={
      "example_id": tf.train.Feature(int64_list=tf.train.Int64List(value=[example_feaures['example_id']])),
      "root_label": tf.train.Feature(int64_list=tf.train.Int64List(value=example_feaures['root_label'])),
      "root_binary_label": tf.train.Feature(int64_list=tf.train.Int64List(value=example_feaures['root_binary_label'])),
      "word_length": tf.train.Feature(int64_list=tf.train.Int64List(value=[example_feaures['length']])),
      "word_ids": tf.train.Feature(int64_list=tf.train.Int64List(value=[example_feaures['word_ids']])),

    })
    return features


  def load_data(self):
    data_splits = ["train", "test", "dev"]
    self.data = {}
    for tag in data_splits:
      file = os.path.join(self.data_path, tag + ".txt")
      print("Loading %s trees.." % file)
      with open(file, 'r') as fid:
        self.data[tag] = [Tree(line) for line in fid.readlines()]


  def build_tfrecords(self,tf_feature_fn, mode, feature_type="tree"):
    tf_example_features = []
    for example in self.get_examples(mode):
      if example['root_label'] != 2:
       tf_example_features.append(tf_feature_fn(example))

    with tf.python_io.TFRecordWriter(os.path.join(self.data_path,feature_type+"_" + mode + ".tfr")) as tf_record_writer:
      for example in tqdm(tf_example_features):
        tf_record = tf.train.Example(features=example)
        tf_record_writer.write(tf_record.SerializeToString())

  @staticmethod
  def parse_sst_tree_examples(example):
    """Load an example from TF record format."""
    features = {"example_id": tf.FixedLenFeature([], tf.int64),
                "length": tf.FixedLenFeature([], tf.int64),
                "is_leaf": tf.FixedLenSequenceFeature([], tf.int64, allow_missing=True),
                "left_children": tf.FixedLenSequenceFeature([], tf.int64, allow_missing=True),
                "right_children": tf.FixedLenSequenceFeature([], tf.int64, allow_missing=True),
                "node_word_ids": tf.FixedLenSequenceFeature([], tf.int64, allow_missing=True),
                "labels": tf.FixedLenSequenceFeature([], tf.int64, allow_missing=True),
                "binary_labels": tf.FixedLenSequenceFeature([], tf.int64, allow_missing=True)}
    parsed_example = tf.parse_single_example(example, features=features)

    example_id = parsed_example["example_id"]
    length = parsed_example["length"]
    tf.logging.info(length)
    is_leaf = parsed_example["is_leaf"]
    tf.logging.info(is_leaf)
    left_children = parsed_example["left_children"]
    right_children = parsed_example["right_children"]
    node_word_ids = parsed_example["node_word_ids"]
    labels = parsed_example["labels"]
    binary_labels = parsed_example["binary_labels"]

    return example_id, length, is_leaf, left_children, right_children, node_word_ids, labels, binary_labels

  @staticmethod
  def parse_full_sst_tree_examples(example):
    """Load an example from TF record format."""
    features = {"example_id": tf.FixedLenFeature([], tf.int64),
                "length": tf.FixedLenFeature([], tf.int64),
                "is_leaf": tf.FixedLenSequenceFeature([], tf.int64, allow_missing=True),
                "left_children": tf.FixedLenSequenceFeature([], tf.int64, allow_missing=True),
                "right_children": tf.FixedLenSequenceFeature([], tf.int64, allow_missing=True),
                "node_word_ids": tf.FixedLenSequenceFeature([], tf.int64, allow_missing=True),
                "labels": tf.FixedLenSequenceFeature([], tf.int64, allow_missing=True),
                "binary_labels": tf.FixedLenSequenceFeature([], tf.int64, allow_missing=True),
                "root_label": tf.FixedLenFeature([], tf.int64),
                "root_binary_label": tf.FixedLenFeature([], tf.int64),
                "word_length": tf.FixedLenFeature([], tf.int64),
                "word_ids": tf.FixedLenSequenceFeature([], tf.int64, allow_missing=True),
                }

    parsed_example = tf.parse_single_example(example, features=features)

    example_id = parsed_example["example_id"]
    length = parsed_example["length"]
    tf.logging.info(length)
    is_leaf = parsed_example["is_leaf"]
    tf.logging.info(is_leaf)
    left_children = parsed_example["left_children"]
    right_children = parsed_example["right_children"]
    node_word_ids = parsed_example["node_word_ids"]
    labels = parsed_example["labels"]
    binary_labels = parsed_example["binary_labels"]

    root_label = parsed_example["root_label"]
    root_binary_label = parsed_example["root_binary_label"]
    word_length = parsed_example["word_length"]
    word_ids = parsed_example["word_ids"]

    return example_id, length, is_leaf, left_children, right_children, node_word_ids, labels, binary_labels,\
           root_label, root_binary_label, word_length, word_ids


  @staticmethod
  def get_padded_shapes():
    return [], [], [None], [None], [None], [None], [None], [None], [], [], [], [None]

  @staticmethod
  def get_tfrecord_path(datapath, mode, feature_type="full"):
    return os.path.join(datapath, feature_type + "_" + mode + ".tfr")

def build_sst():

  sst_prep = SST(data_path="data/sst/")
  sst_prep.load_data()
  sst_prep.build_tfrecords("train")
  sst_prep.build_tfrecords("dev")
  sst_prep.build_tfrecords("test")

def build_full_sst():
  sst_prep = SST(data_path="data/sst/")
  sst_prep.load_data()

  sst_prep.build_tfrecords(sst_prep.get_all_tf_features, mode="train", feature_type="full")
  sst_prep.build_tfrecords(sst_prep.get_all_tf_features, mode="dev", feature_type="full")
  sst_prep.build_tfrecords(sst_prep.get_all_tf_features, mode="test", feature_type="full")

def build_sst_main():
  build_sst()

  dataset = tf.data.TFRecordDataset(SST.get_tfrecord_path("data/sst", mode="train"))
  dataset = dataset.map(SST.parse_sst_tree_examples)
  dataset = dataset.padded_batch(10, padded_shapes=SST.get_padded_shapes())
  iterator = dataset.make_initializable_iterator()

  example = iterator.get_next()
  example_id, length, is_leaf, left_children, right_children, node_word_ids, labels, binary_labels = example
  global_step = tf.train.get_or_create_global_step()
  scaffold = tf.train.Scaffold(local_init_op=tf.group(tf.local_variables_initializer(),
                                                      iterator.initializer))
  with tf.train.MonitoredTrainingSession(checkpoint_dir='logs', scaffold=scaffold) as sess:
    print(sess.run(labels))

def test():
  batch_size = 10
  dataset = tf.data.TFRecordDataset(SST.get_tfrecord_path("data/sst", mode="train", feature_type="full"))
  dataset = dataset.map(SST.parse_full_sst_tree_examples)
  dataset = dataset.padded_batch(batch_size, padded_shapes=SST.get_padded_shapes())
  iterator = dataset.make_initializable_iterator()

  example = iterator.get_next()
  example_id, length, is_leaf, left_children, right_children, node_word_ids, labels, binary_labels, \
      root_label, root_binary_label, word_length, word_ids = example

  bach_indices = tf.expand_dims(tf.range(batch_size), 1)
  root_indices = tf.concat([bach_indices, tf.expand_dims(tf.cast(length - 1, dtype=tf.int32), 1)], axis=-1)

  computed_root_label = tf.gather_nd(labels, root_indices)
  computed_root_binary_label = tf.gather_nd(binary_labels, root_indices)

  global_step = tf.train.get_or_create_global_step()
  scaffold = tf.train.Scaffold(local_init_op=tf.group(tf.local_variables_initializer(),
                                                      iterator.initializer))
  with tf.train.MonitoredTrainingSession(checkpoint_dir='logs', scaffold=scaffold) as sess:
    out_root_label, out_root_binary_label, out_labels, out_binary_labels, out_computed_root_label, out_computed_root_binary_label= \
      sess.run([root_label, root_binary_label,labels, binary_labels, computed_root_label, computed_root_binary_label])
    out_word_ids = sess.run(word_ids)

    print(out_word_ids)

    print(list(zip(out_root_label,out_computed_root_label)))
    print(out_root_binary_label[0])
    print(out_computed_root_label[0])
    print(out_computed_root_binary_label[0])

if __name__ == '__main__':
  build_full_sst()
  test()
