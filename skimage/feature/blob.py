import numpy as np
from scipy.ndimage.filters import gaussian_filter, gaussian_laplace
import itertools as itt
import math
from math import sqrt, hypot, log
from numpy import arccos
from skimage.util import img_as_float
from .peak import peak_local_max


# This basic blob detection algorithm is based on:
# http://www.cs.utah.edu/~jfishbau/advimproc/project1/ (04.04.2013)
# Theory behind: http://en.wikipedia.org/wiki/Blob_detection (04.04.2013)


def _blob_overlap(blob1, blob2):
    """Finds the overlapping area fraction between two blobs.

    Returns a float representing fraction of overlapped area.

    Parameters
    ----------
    blob1 : sequence
        A sequence of ``(y,x,sigma)``, where ``x,y`` are coordinates of blob
        and sigma is the standard deviation of the Gaussian kernel which
        detected the blob.
    blob2 : sequence
        A sequence of ``(y,x,sigma)``, where ``x,y`` are coordinates of blob
        and sigma is the standard deviation of the Gaussian kernel which
        detected the blob.

    Returns
    -------
    f : float
        Fraction of overlapped area.

    """
    root2 = sqrt(2)

    # extent of the blob is given by sqrt(2)*scale
    r1 = blob1[2] * root2
    r2 = blob2[2] * root2

    d = hypot(blob1[0] - blob2[0], blob1[1] - blob2[1])

    if d > r1 + r2:
        return 0

    # one blob is inside the other, the smaller blob must die
    if d <= abs(r1 - r2):
        return 1

    acos1 = arccos((d ** 2 + r1 ** 2 - r2 ** 2) / (2 * d * r1))
    acos2 = arccos((d ** 2 + r2 ** 2 - r1 ** 2) / (2 * d * r2))
    a = -d + r2 + r1
    b = d - r2 + r1
    c = d + r2 - r1
    d = d + r2 + r1
    area = r1 ** 2 * acos1 + r2 ** 2 * acos2 - 0.5 * sqrt(abs(a * b * c * d))

    return area / (math.pi * (min(r1, r2) ** 2))


def _prune_blobs(blobs_array, overlap):
    """Eliminated blobs with area overlap.

    Parameters
    ----------
    blobs_array : ndarray
        a 2d array with each row representing 3 values, the ``(y,x,sigma)``
        where ``(y,x)`` are coordinates of the blob and sigma is the standard
        deviation of the Gaussian kernel which detected the blob.
    overlap : float
        A value between 0 and 1. If the fraction of area overlapping for 2
        blobs is greater than `overlap` the smaller blob is eliminated.

    Returns
    -------
    A : ndarray
        `array` with overlapping blobs removed.

    """

    # iterating again might eliminate more blobs, but one iteration suffices
    # for most cases
    for blob1, blob2 in itt.combinations(blobs_array, 2):
        if _blob_overlap(blob1, blob2) > overlap:
            if blob1[2] > blob2[2]:
                blob2[2] = -1
            else:
                blob1[2] = -1

    # return blobs_array[blobs_array[:, 2] > 0]
    return np.array([b for b in blobs_array if b[2] > 0])


def blob_dog(image, min_sigma=1, max_sigma=50, sigma_ratio=1.6, threshold=2.0,
             overlap=.5,):
    """Finds blobs in the given grayscale image.

    Blobs are found using the Difference of Gaussian (DoG) method[1]_.
    For each blob found, its coordinates and area are returned.

    Parameters
    ----------
    image : ndarray
        Input grayscale image, blobs are assumed to be light on dark
        background (white on black).
    min_sigma : float, optional
        The minimum standard deviation for Gaussian Kernel. Keep this low to
        detect smaller blobs.
    max_sigma : float, optional
        The maximum standard deviation for Gaussian Kernel. Keep this high to
        detect larger blobs.
    sigma_ratio : float, optional
        The ratio between the standard deviation of Gaussian Kernels used for
        computing the Difference of Gaussians
    threshold : float, optional.
        The absolute lower bound for scale space maxima. Local maxima smaller
        than thresh are ignored. Reduce this to detect blobs with less
        intensities.
    overlap : float, optional
        A value between 0 and 1. If the area of two blobs overlaps by a
        fraction greater than `threshold`, the smaller blob is eliminated.

    Returns
    -------
    A : (n, 3) ndarray
        A 2d array with each row containing the Y-Coordinate , the
        X-Coordinate and the estimated area of the blob respectively.

    References
    ----------
    .. [1] http://en.wikipedia.org/wiki/Blob_detection#The_difference_of_Gaussians_approach

    Examples
    --------
    >>> from skimage import data, feature
    >>> feature.blob_dog(data.coins(),threshold=.5,max_sigma=40)
    array([[  45,  336, 1608],
           [  52,  155, 1608],
           [  52,  216, 1608],
           [  54,   42, 1608],
           [  54,  276,  628],
           [  58,  100,  628],
           [ 120,  272, 1608],
           [ 124,  337,  628],
           [ 125,   45, 1608],
           [ 125,  208,  628],
           [ 127,  102,  628],
           [ 128,  154,  628],
           [ 185,  347, 1608],
           [ 193,  213, 1608],
           [ 194,  277, 1608],
           [ 195,  102, 1608],
           [ 196,   43,  628],
           [ 198,  155,  628],
           [ 260,   46, 1608],
           [ 261,  173, 1608],
           [ 263,  245, 1608],
           [ 263,  302, 1608],
           [ 267,  115,  628],
           [ 267,  359, 1608]])

    """

    if image.ndim != 2:
        raise ValueError("'image' must be a grayscale ")

    image = img_as_float(image)

    # k such that min_sigma*(sigma_ratio**k) > max_sigma
    k = int(log(float(max_sigma) / min_sigma, sigma_ratio)) + 1

    # a geometric progression of standard deviations for gaussian kernels
    sigma_list = np.array([min_sigma * (sigma_ratio ** i)
                          for i in range(k + 1)])

    gaussian_images = [gaussian_filter(image, s) for s in sigma_list]

    # computing difference between two successive Gaussian blurred images
    # multiplying with standard deviation provides scale invariance
    dog_images = [(gaussian_images[i] - gaussian_images[i + 1])
                  * sigma_list[i] for i in range(k)]
    image_cube = np.dstack(dog_images)

    # local_maxima = get_local_maxima(image_cube, threshold)
    local_maxima = peak_local_max(image_cube, threshold_abs=threshold,
                                  footprint=np.ones((3, 3, 3)),
                                  threshold_rel=0.0,
                                  exclude_border=False)

    # Convert the last index to its corresponding scale value
    local_maxima[:, 2] = sigma_list[local_maxima[:, 2]]
    ret_val = _prune_blobs(local_maxima, overlap)

    if len(ret_val) > 0:
        ret_val[:, 2] = math.pi * \
            ((ret_val[:, 2] * math.sqrt(2)) ** 2).astype(int)
        return ret_val
    else:
        return []


def blob_log(image, min_sigma=1, max_sigma=50, num_sigma=10, threshold=.1,
             overlap=.5, log_scale=False):
    """Finds blobs in the given grayscale image.

    Blobs are found using the Laplacian of Gaussian (DoG) method[1]_.
    For each blob found, its coordinates and area are returned.

    Parameters
    ----------
    image : ndarray
        Input grayscale image, blobs are assumed to be light on dark
        background (white on black).
    min_sigma : float, optional
        The minimum standard deviation for Gaussian Kernel. Keep this low to
        detect smaller blobs.
    max_sigma : float, optional
        The maximum standard deviation for Gaussian Kernel. Keep this high to
        detect larger blobs.
    num_sigma : int, optional
        The number of intermediate values of standard deviations to consider
        between `min_sigma` and `max_sigma`.
    threshold : float, optional.
        The absolute lower bound for scale space maxima. Local maxima smaller
        than thresh are ignored. Reduce this to detect blobs with less
        intensities.
    overlap : float, optional
        A value between 0 and 1. If the area of two blobs overlaps by a
        fraction greater than `threshold`, the smaller blob is eliminated.
    log_scale : bool, optional
        If set intermediate values of standard deviations are interpolated
        using a logarithmic scale to the base `10`. If not, linear
        interpolation is used.

    Returns
    -------
    A : (n, 3) ndarray
        A 2d array with each row containing the Y-Coordinate , the
        X-Coordinate and the estimated area of the blob respectively.

    References
    ----------
    .. [1] http://en.wikipedia.org/wiki/Blob_detection#The_Laplacian_of_Gaussian

    Examples
    --------
    >>> from skimage import data, feature, exposure
    >>> img = data.coins()
    >>> img = exposure.equalize_hist(img) # imporves detection
    >>> feature.blob_log(img,threshold = .3)
    array([[ 107,  333,    6],
           [ 107,  337,   25],
           [ 108,  329,    6],
           [ 113,  323,    6],
           [ 114,  322,    6],
           [ 121,  273, 1608],
           [ 124,  336,  904],
           [ 125,   45, 1061],
           [ 125,  207,  904],
           [ 127,  102,  760],
           [ 128,  155,  760],
           [ 178,  261,   25],
           [ 186,  345, 2268],
           [ 193,  276, 1413],
           [ 194,  213, 1413],
           [ 196,  102, 1061],
           [ 197,   43,  904],
           [ 198,  155,  904],
           [ 198,  255,   56],
           [ 214,  282,   25],
           [ 260,  174, 1608],
           [ 262,  244, 1413],
           [ 262,  302, 1413],
           [ 266,  114, 1061],
           [ 268,  358, 1061]])

    """

    if image.ndim != 2:
        raise ValueError("'image' must be a grayscale ")

    image = img_as_float(image)

    if log_scale:
        sigma_list = np.linspace(min_sigma, max_sigma, num_sigma)
    else:
        start, stop = log(min_sigma, 10), log(max_sigma, 10)
        sigma_list = np.logspace(start, stop)

    gl_images = [-gaussian_laplace(image, s) * s ** 2 for s in sigma_list]
    image_cube = np.dstack(gl_images)

    local_maxima = peak_local_max(image_cube, threshold_abs=threshold,
                                  footprint=np.ones((3, 3, 3)),
                                  threshold_rel=0.0,
                                  exclude_border=False)

    # Convert the last index to its corresponding scale value
    local_maxima[:, 2] = sigma_list[local_maxima[:, 2]]
    ret_val = _prune_blobs(local_maxima, overlap)

    if len(ret_val) > 0:
        ret_val[:, 2] = math.pi * \
            ((ret_val[:, 2] * math.sqrt(2)) ** 2).astype(int)
        return ret_val
    else:
        return []
