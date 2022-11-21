#!/usr/bin/env python3

# ============================

import torch
import torch.nn.functional as F
import torchvision
from PIL import Image
import json

device = "cuda" if torch.cuda.is_available() else "cpu"
as_numpy = lambda x: x.detach().cpu().numpy()

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cm as cm

jet = cm.get_cmap("jet")
jet_colors = jet(np.arange(256))[:, :3]

def show_result(img, saliency, label = ""):
    img = np.array(img, dtype = float) / 255.0

    saliency = F.interpolate(saliency, size = img.shape[:2], mode = "bilinear")
    #print(img.shape)
    #print("before",saliency.shape)
    saliency = as_numpy(saliency)[0, 0]
    #print("after", saliency.shape)
    saliency = saliency - saliency.min()
    saliency = np.uint8(255 * saliency / saliency.max())
    heatmap = jet_colors[saliency]
    plt.imshow(0.5 * heatmap + 0.5 * img)
    plt.axis("off")
    plt.title(label)
    plt.show()

def show_fmap(img, saliency, scores):
    img = np.array(img, dtype = float) / 255.0

    saliency = F.interpolate(saliency, size = img.shape[:2], mode = "bilinear")

    ix = 1
    ids=5
    square=4
    for _ in range(square):
        for _ in range(square):
            feature = as_numpy(saliency)[0][ids]
            # print("after", saliency.shape)
            feature = feature - feature.min()
            feature = np.uint8(255 * feature / feature.max())
            heatmap = jet_colors[feature]
            # specify subplot and turn of axis
            ax = plt.subplot(square, square, ix)
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_title("{}: {}".format(ids, scores[ids]))
            #plt.imshow(heatmap)
            plt.imshow(0.5 * heatmap + 0.5 * img)
            ix += 1
            ids += 100
    plt.show()


# define the preprocessing transform
image_shape = (224, 224)

transform = torchvision.transforms.Compose(
    [
        torchvision.transforms.Resize(image_shape),
        torchvision.transforms.ToTensor(),
        torchvision.transforms.Normalize(
            mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]
        ),
    ]
)

with open("data/imagenet_class_index.json") as f:
    indx2label = json.load(f)


def decode_predictions(preds, k=5):
    # return the top k results in the predictions
    return [
        [(*indx2label[str(i)], i, pred[i]) for i in pred.argsort()[::-1][:k]]
        for pred in as_numpy(preds)
    ]

class Probe:
    def get_hook(self,):
        self.data = []
        def hook(module, input, output):
            self.data.append(output)
        return hook


# load the image
print("loading the image...")
img = Image.open("./data/shark.jpeg")

x = transform(img)[None]  # transform and reshape it to [1, C, *image_shape]
x = x.to(device)

print("loading the model...")
### You can change the model here.
model = torchvision.models.resnet50(pretrained=True)
model.eval()
model.to(device)

#add a probe to model
probe = Probe()
#probe will save the output of the layer4 during forward
handle = model.layer4.register_forward_hook(probe.get_hook())

logits = model(x)
preds = logits.softmax(-1)

print("the prediction result:")
for tag, label, i, prob in decode_predictions(preds)[0]:
    print("{} {:16} {:5} {:6.2%}".format(tag, label, i, prob))

print("Calculating the saliency of the top prediction...")
target = preds.argmax().item()

### Grad_Cam
# get the last_conv_output
last_conv_output = probe.data[0]
handle.remove()

last_conv_output.retain_grad() #make sure the intermediate result save its grad

#backprop
logits[0, target].backward()
grad = last_conv_output.grad 
#taking average on the H-W panel
weight = grad.mean(dim = (-1, -2), keepdim = True)

scores = weight[0,:,0,0]
show_fmap(img, last_conv_output,scores)

saliency = (last_conv_output * weight).sum(dim = 1, keepdim = True)

#relu

saliency = saliency.clamp(min = 0)

show_result(img, saliency, "grad_cam on {} {}".format(*indx2label[str(target)]))
