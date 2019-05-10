"""
Copyright (c) College of Mechatronics and Control Engineering, Shenzhen University.
All rights reserved.

Description :


Author：Team Li
"""
import tensorflow as tf
import numpy as np
import logging
import os
import glob

from net.u_net import u_net
from dataset.bdd_daytime import bdd_daytime

from skimage import io
import cv2

tf.app.flags.DEFINE_string(
    'checkpoint_dir', './checkpoint',
    'The path to a checkpoint from which to fine-tune.')

tf.app.flags.DEFINE_string(
    'train_dir', './checkpoint',
    'Directory where checkpoints are written to.')

tf.app.flags.DEFINE_float('learning_rate', 1e-2, 'Initial learning rate.')

tf.app.flags.DEFINE_integer(
    'batch_size', 10, 'The number of samples in each batch.')

tf.app.flags.DEFINE_integer(
    'f_log_step', 5,
    'The frequency with which logs are print.')

tf.app.flags.DEFINE_integer(
    'f_save_step', 1000,
    'The frequency with which summaries are saved, in step.')

tf.app.flags.DEFINE_integer(
    'f_eval_step', 20,
    'The frequency with which summaries are saved, in step.')

FLAGS = tf.app.flags.FLAGS

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

input = tf.placeholder(shape=[None, 139*2, 209*2, 3], dtype=tf.float32)
groundtruth = tf.placeholder(shape=[None, 139*2, 209*2, 3], dtype=tf.float32)
# input = tf.placeholder(shape=[None, 256, 256, 3], dtype=tf.float32)
# groundtruth = tf.placeholder(shape=[None, 256, 256, 3], dtype=tf.float32)
global_step = tf.Variable(0, trainable=False, name='global_step')

lr = tf.placeholder(dtype=tf.float32)

def _smooth_l1(x):
    """Smoothed absolute function. Useful to compute an L1 smooth error.
    Define as:
        x^2 / 2         if abs(x) < 1
        abs(x) - 0.5    if abs(x) > 1
    We use here a differentiable definition using min(x) and abs(x). Clearly
    not optimal, but good enough for our purpose!
    """
    absx = tf.abs(x)
    minx = tf.minimum(absx, 1)
    r = 0.5 * ((absx - 1) * minx + absx)  ## smooth_l1
    return r

def build_graph(input):
    output = u_net(input, is_training=True)

    loss = tf.reduce_sum(_smooth_l1(output - groundtruth)) / FLAGS.batch_size

    update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
    with tf.control_dependencies(update_ops):
        optimizer = tf.train.AdamOptimizer(learning_rate=lr)

        grads_and_vars = optimizer.compute_gradients(loss)
        ## clip the gradients ##
        capped_gvs = [(tf.clip_by_value(grad, -5., 5.), var)
                      for grad, var in grads_and_vars]
        train_op = optimizer.apply_gradients(capped_gvs, global_step=global_step)

    return output, loss, train_op

def main(_):
    output, loss, train_op = build_graph(input)

    logger.info('Total trainable parameters:%s'%(str(np.sum([np.prod(v.get_shape().as_list()) \
                                                             for v in tf.trainable_variables()]))))

    saver = tf.train.Saver()

    ckpt = tf.train.get_checkpoint_state(FLAGS.checkpoint_dir)
    init = tf.global_variables_initializer()

    config = tf.ConfigProto()
    config.gpu_options.allow_growth = True
    with tf.Session(config=config) as sess:
        pd = bdd_daytime(batch_size=FLAGS.batch_size, for_what='train', shuffle=True)

        if ckpt:
            logger.info('loading %s...'%str(ckpt.model_checkpoint_path))
            saver.restore(sess, ckpt.model_checkpoint_path)
            logger.info('load %s success...'%str(ckpt.model_checkpoint_path))
        else:
            sess.run(init)
            logger.info('Init Tf parameters success...')

        avg_loss = 0.
        current_step  = sess.run(global_step)
        while current_step < 80000:
            if current_step<20000:
                learning_rate = FLAGS.learning_rate
            elif current_step<40000:
                learning_rate = FLAGS.learning_rate / 10.
            else:
                learning_rate = FLAGS.learning_rate / 10.

            gt_imgs, train_imgs = pd.load_batch()

            update_op, l, current_step = sess.run([train_op, loss, global_step],
                                                  feed_dict={input:train_imgs,
                                                             groundtruth:gt_imgs,
                                                             lr:learning_rate})

            if FLAGS.f_log_step != None:
                ## caculate average loss ##
                step = current_step % FLAGS.f_log_step
                avg_loss = (avg_loss * step + l) / (step + 1.)

                if current_step % FLAGS.f_log_step == FLAGS.f_log_step - 1:
                    ## print info ##
                    logger.info('Step%s loss:%s' % (str(current_step), str(avg_loss)))
                    avg_loss = 0.

            if FLAGS.f_save_step != None:
                if current_step % FLAGS.f_save_step == FLAGS.f_save_step - 1:
                    ## save model ##
                    logger.info('Saving model...')
                    model_name = os.path.join(FLAGS.train_dir, 'dark_aug.model')
                    saver.save(sess, model_name)
                    logger.info('Save model sucess...')

            # if FLAGS.f_eval_step != None:
            #     if current_step % FLAGS.f_eval_step == FLAGS.f_eval_step - 1:
            #         files = glob.glob('./dark/*.jpg')
            #         for file in files:
            #             img = io.imread(file)
            #             img = cv2.resize(img, dsize=(209, 139))
            #             img = img*2./255. - 1.
            #             out = sess.run(output, feed_dict={input:np.array([img])})
            #             img = np.uint8((out[0]+1.)*255/2)
            #
            #             file_name = os.path.basename(file).split('.')[0] + '_' +str(current_step) +'.jpg'
            #             io.imsave('./eval/%s'%(file_name), img)


if __name__ == '__main__':
    tf.app.run()

