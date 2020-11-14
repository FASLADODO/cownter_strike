import torchvision
import torch
from haven import haven_utils as hu
import numpy as np
from torchvision.transforms import transforms
from sklearn.utils import shuffle
from PIL import Image
from . import pascal, cows

from src import utils as ut
import os
import os
import numpy as np

import random
import torch
from torch.utils.data import Dataset
from torchvision.transforms import functional as F
from PIL import Image
from . import mnist


def get_dataset(dataset_dict, split, datadir, exp_dict, dataset_size=None):
    name = dataset_dict['name']
    # load dataset
    if name in ['cows', 'cows_json']:
        dataset = cows.Cows(datadir, split=split, exp_dict=exp_dict)

        if dataset_size is not None and dataset_size.get(split, 'all') != 'all':
            dataset.meta_list = dataset.meta_list[:dataset_size[split]]
            dataset.labels = dataset.labels[:dataset_size[split]]

    elif name == "mnist_binary":
        dataset = mnist.Mnist(split=split, binary=True, datadir_base=datadir)
        if dataset_size is not None and dataset_size.get(split, 'all') != 'all':
            dataset.dataset.data = dataset.dataset.data[:dataset_size[split]]
            dataset.dataset.targets = dataset.dataset.targets[:dataset_size[split]]

    elif name == "mnist_full":
        dataset = mnist.Mnist(split=split, binary=False, datadir_base=datadir)
        
    elif name in ['cows', 'cows_v1']:
        path = os.path.join(datadir, 'v1')
        dataset = cows.Cows(path, split=split, exp_dict=exp_dict)

        if dataset_size is not None and dataset_size.get(split, 'all') != 'all':
            dataset.meta_list = dataset.meta_list[:dataset_size[split]]


    elif name == 'cows_v2':
        path = os.path.join(datadir, 'v2_cows')
        dataset = cows.Cows(path, split=split, exp_dict=exp_dict)

        if dataset_size is not None and dataset_size.get(split, 'all') != 'all':
            dataset.meta_list = dataset.meta_list[:dataset_size[split]]


    elif name == 'cows_v1_v2':
        path_list = [os.path.join(datadir, 'v1'), os.path.join(datadir, 'v2_cows')]
        dataset = cows.Cows(path_list, split=split, exp_dict=exp_dict)

        if dataset_size is not None and dataset_size.get(split, 'all') != 'all':
            dataset.meta_list = dataset.meta_list[:dataset_size[split]]



    elif name == 'pascal':
        # datadir = os.path.join('/mnt/datasets/public/issam/')
        
        dataset = pascal.Pascal(datadir, split=split, supervision='full', 
                                exp_dict=exp_dict,
                                sbd=exp_dict['dataset'].get('sbd', False))

        if dataset_size is not None and dataset_size.get(split, 'all') != 'all':
            dataset.dataset.images = dataset.dataset.images[:dataset_size[split]]

    elif name == "cityscapes":
        datadir_base = '/mnt/datasets/public/issam/'
        datadir = os.path.join(datadir_base)
        dataset = cityscapes.CityScapes(split=split, exp_dict=exp_dict)
        if dataset_size is not None and dataset_size.get(split, 'all') != 'all':
            dataset.dataset.images = dataset.dataset.images[:dataset_size[split]]
     
    else:
        raise ValueError('dataset %s not found' % name)

    print(split, ':', len(dataset))
    return dataset

def get_random(y_list, x_list):
    with hu.random_seed(1):
        yi = np.random.choice(y_list)
        x_tmp = x_list[y_list == yi]
        xi = np.random.choice(x_tmp)

    return yi, xi

def get_median(y_list, x_list):
    tmp = y_list
    mid = max(0, len(tmp)//2 - 1)
    yi = tmp[mid]
    tmp = x_list[y_list == yi]
    mid = max(0, len(tmp)//2 - 1)
    xi = tmp[mid]

    return yi, xi

class BatchDictator:
    def __init__(self, split, n_classes):
        self.n_classes = n_classes 

        # irn stuff
        self.scales = (1.0,)
        if split == 'train':
            self.resize_long = (320, 640)
            self.rescale = None
            self.crop_size = 512
            self.img_normal = TorchvisionNormalize()
            self.hor_flip = True
            self.crop_method = "random"
            self.to_torch = True

        elif split == 'val':
            self.resize_long = None
            self.rescale = None
            self.crop_size = 512
            self.img_normal = TorchvisionNormalize()
            self.hor_flip = None
            self.crop_method = None
            self.to_torch = True

    def get_batch(self, img_pil, mask_pil, transforms, idx, class_pil=None, 
                       void=255, inst_pil=None, name=None, points=None):

        if inst_pil is not None:
            mask = np.array(inst_pil)
            mask_void = mask == void
            mask[mask_void] = 0
        else:
            mask = np.array(mask_pil)
            mask_void = mask == void
            mask[mask_void] = 0
        
        # instances are encoded as different colors
        obj_ids = np.unique(mask)
        # first id is the background, so remove it
        obj_ids = obj_ids[1:]

        # split the color-encoded mask into a set
        # of binary masks
        masks = mask == obj_ids[:, None, None]

        # get bounding box coordinates for each mask
        num_objs = len(obj_ids)
        # if num_objs == 0:
        #     raise ValueError('should have car')

        boxes = []
        for i in range(num_objs):
            pos = np.where(masks[i])
            xmin = np.min(pos[1])
            xmax = np.max(pos[1])
            ymin = np.min(pos[0])
            ymax = np.max(pos[0])
            boxes.append([xmin, ymin, xmax, ymax])

        boxes = torch.as_tensor(boxes, dtype=torch.float32)
        # there is only one class
        if inst_pil is not None:
            mask_color = np.array(mask_pil)
            labels = []
            for m in masks:
                labels += [(mask_color*m).max()]
            labels = torch.LongTensor(labels)
        else:
            labels = torch.ones((num_objs,), dtype=torch.int64)
        masks = torch.as_tensor(masks, dtype=torch.uint8)

        image_id = torch.tensor([idx])
        if num_objs == 0:
            area = torch.tensor([])
        else:
            area = (boxes[:, 3] - boxes[:, 1]) * (boxes[:, 2] - boxes[:, 0])
        # suppose all instances are not crowd
        iscrowd = torch.zeros((num_objs,), dtype=torch.int64)

        target = {}
        target["boxes"] = boxes
        target["labels"] = labels
        target["masks"] = masks
        target["image_id"] = image_id
        target["area"] = area
        target["iscrowd"] = iscrowd

        if transforms is not None and len(boxes):
            img, target = transforms(img_pil, target)
        else:
            import torchvision
            img = torchvision.transforms.ToTensor()(img_pil)
            target = None

        labels_tensor = torch.zeros(self.n_classes-1)
        labels_tensor[labels-1] = 1
        # return img, target
        batch_dict = {'images':img, 
                    'mask_pil':mask_pil,
                    'image_pil':img_pil,
                    'original':np.array(img_pil),
                    'inst_pil':inst_pil,
                    'label':labels_tensor,
                    'points':points,
                    'mask_void':torch.FloatTensor(mask_void),
                    'targets': target,
                    'meta':{'index':idx, 'name':name}}

        return batch_dict
        
    def transform_img(self, img_org):
        img = img_org

        if self.resize_long:
            img = imutils.random_resize_long(img, self.resize_long[0], self.resize_long[1])

        if self.rescale:
            img = imutils.random_scale(img, scale_range=self.rescale, order=3)

        if self.img_normal:
            img = self.img_normal(img)

        if self.hor_flip:
            img = imutils.random_lr_flip(img)

        if self.crop_size:
            if self.crop_method == "random":
                img = imutils.random_crop(img, self.crop_size, 0)
            else:
                img = imutils.top_left_crop(img, self.crop_size, 0)

        if self.to_torch:
            img = imutils.HWC_to_CHW(img)

        return img

    def get_cam_batch(self, img_org):
        batch = {}
        img = self.transform_img(img_org)
        ms_img_list = self.get_multi_scale(img_org)
        
        batch['img'] =  torch.from_numpy(img)
        batch['img_msf'] =  ms_img_list
        batch['size'] = (img_org.shape[0], img_org.shape[1])

        return batch

    def get_multi_scale(self, img_org):
        img = img_org

        ms_img_list = []
        for s in self.scales:
            if s == 1:
                s_img = img
            else:
                s_img = imutils.pil_rescale(img, s, order=3)

            s_img = self.img_normal(s_img)
            s_img = imutils.HWC_to_CHW(s_img)
            ms_img_list.append(np.stack([s_img, np.flip(s_img, -1)], axis=0))

        if len(self.scales) == 1:
            ms_img_list = ms_img_list[0]

        out =  torch.from_numpy(ms_img_list)

        return out
