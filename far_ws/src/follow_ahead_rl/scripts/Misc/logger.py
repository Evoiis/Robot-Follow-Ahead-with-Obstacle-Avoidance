from tensorboardX import SummaryWriter
import logging

logger = logging.getLogger(__name__)


class Logger(object):

    def __init__(self, log_dir, name, project_name="follow_ahead_d4pg_v0.1newplannerdense600numa41", use_wandb=False, reinit=False):
        """
        General logger.

        Args:
            log_dir (str): log directory
        """

        self.writer = SummaryWriter(log_dir)
        self.info = logger.info
        self.debug = logger.debug
        self.warning = logger.warning

    def image_summar(self, tag, image, step):
        self.writer.add_image(tag, image, step, dataformats='HWC')

    def scalar_summary(self, tag, value, step):
        """
        Log scalar value to the disk.
        Args:
            tag (str): name of the value
            value (float): value
            step (int): update step
        """
        self.writer.add_scalar(tag, value, step)

    def close(self):
        self.writer.close()

