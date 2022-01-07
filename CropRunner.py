"""
** Crop Extractor for Project Sidewalk **

Given label metadata from the Project Sidewalk database, this script will
extract JPEG crops of the features that have been labeled. The required metadata
may be obtained by running the SQL query in "samples/getFullLabelList.sql" on the
Sidewalk database, and exporting the results in CSV format. You must supply the
path to the CSV file containing this data below. You can find an example of what
this file should look like in "samples/labeldata.csv".

Additionally, you should have downloaded original panorama
images from Street View using DownloadRunner.py. You will need to supply the
path to the folder containing these files.

"""

import csv
import logging
import math
import multiprocessing as mp
from itertools import islice
from time import perf_counter
from PIL import Image, ImageDraw
import os

from PIL import ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True

# *****************************************
# Update paths below                      *
# *****************************************

# Path to CSV data from database - Place in 'metadata'
csv_export_path = "metadata/gathered_panos.csv"
# Path to panoramas downloaded using DownloadRunner.py. Reference correct directory
gsv_pano_path = "../pano-downloads"
# Path to location for saving the crops
destination_path = "crops"
# Name of csv containing info about crops
csv_crop_info = "crop_info.csv"

# Mark the center of the crop?
mark_center = True

# The number of crops per multicrop
MULTICROP_COUNT = 2

# The scale factor for each multicrop
MULTICROP_SCALE_FACTOR = 1.5

logging.basicConfig(filename='crop.log', level=logging.DEBUG)

def predict_crop_size(sv_image_y):
    """
    # Calculate distance from point to image center
    dist_to_center = math.sqrt((x-im_width/2)**2 + (y-im_height/2)**2)
    # Calculate distance from point to center of left edge
    dist_to_left_edge = math.sqrt((x-0)**2 + (y-im_height/2)**2)
    # Calculate distance from point to center of right edge
    dist_to_right_edge = math.sqrt((x - im_width) ** 2 + (y - im_height/2) ** 2)

    min_dist = min([dist_to_center, dist_to_left_edge, dist_to_right_edge])

    crop_size = (4.0/15.0)*min_dist + 200

    print("Min dist was "+str(min_dist))
    """
    crop_size = 0
    distance = max(0, 19.80546390 + 0.01523952 * sv_image_y)

    if distance > 0:
        crop_size = 8725.6 * (distance ** -1.192)
    if crop_size > 1500 or distance == 0:
        crop_size = 1500
    if crop_size < 50:
        crop_size = 50

    return crop_size

def make_crop(pano_img_path, sv_image_x, sv_image_y, pano_yaw_deg, photographer_pitch, destination_dir, label_name, lock, multicrop=True, draw_mark=True):
    """
    Makes a crop around the object of interest
    :param path_to_image: where the GSV pano is stored
    :param sv_image_x: position
    :param sv_image_y: position
    :param PanoYawDeg: heading
    :param destination_dir: path of the crop directory
    :param label_name: label name
    :param multicrop: whether or not to make multiple crops for the label
    :param draw_mark: if a dot should be drawn in the centre of the object/image
    :return: crop_names: a list of crop_names
    """
    crop_names = []
    try:
        im = Image.open(pano_img_path)
        draw = ImageDraw.Draw(im)

        im_width = im.size[0]
        im_height = im.size[1]
        # print(im_width, im_height)

        predicted_crop_size = predict_crop_size(sv_image_y)
        # crop_width = int(predicted_crop_size)
        # crop_height = int(predicted_crop_size)
        crop_width = 1500
        crop_height = 1500

        # Work out scaling factor based on image dimensions
        scaling_factor = im_width / 13312
        sv_image_x *= scaling_factor
        sv_image_y *= scaling_factor

        y_adjustment = im_height * photographer_pitch / 180

        x = ((float(pano_yaw_deg) / 360) * im_width + sv_image_x) % im_width
        y = im_height / 2 - sv_image_y

        new_y = im_height / 2 - sv_image_y + y_adjustment

        # print("old y, new y: ", old_y, y)

        r = 50
        if draw_mark:
            lock.acquire()
            draw.ellipse((x - r, y - r, x + r, y + r), fill=128)
            im.save(pano_img_path)
            lock.release()

        # print("Plotting at " + str(x) + "," + str(y) + " using yaw " + str(pano_yaw_deg))

        # print(x, y)
        for i in range(MULTICROP_COUNT):
            top_left_x = int(x - crop_width / 2)
            top_left_y = int(y - crop_height / 2)
            if multicrop:
                crop_name = label_name + "_" + str(i) + ".jpg"
            else:
                crop_name = label_name + ".jpg"
            crop_destination = os.path.join(destination_dir, crop_name)
            if not os.path.exists(crop_destination) and 0 <= top_left_y and top_left_y + crop_height <= im_height:
                crop = Image.new('RGB', (crop_width, crop_height))
                if top_left_x < 0:
                    crop_1 = im.crop((top_left_x + im_width, top_left_y, im_width, top_left_y + crop_height))
                    crop_2 = im.crop((0, top_left_y, top_left_x + crop_width, top_left_y + crop_height))
                    crop.paste(crop_1, (0,0))
                    crop.paste(crop_2, (- top_left_x, 0))
                elif top_left_x + crop_width > im_width:
                    crop_1 = im.crop((top_left_x, top_left_y, im_width, top_left_y + crop_height))
                    crop_2 = im.crop((0, top_left_y, top_left_x + crop_width - im_width, top_left_y + crop_height))
                    crop.paste(crop_1, (0,0))
                    crop.paste(crop_2, (im_width - top_left_x, 0))
                else:
                    crop = im.crop((top_left_x, top_left_y, top_left_x + crop_width, top_left_y + crop_height))
                crop.save(crop_destination)
                print("Successfully extracted crop to " + crop_name)
                logging.info(label_name + " " + pano_img_path + " " + str(sv_image_x) + " " + str(sv_image_y) + " " + str(pano_yaw_deg))
                logging.info("---------------------------------------------------")
                crop_names.append(crop_name)
            else:
                print("Failed to extract crop to " + crop_name)
            if not multicrop:
                break
            crop_width = int(crop_width * MULTICROP_SCALE_FACTOR)
            crop_height = int(crop_height * MULTICROP_SCALE_FACTOR)
        im.close()
    except Exception as e:
        print(e)
        print("Error for {}".format(pano_img_path))

    return crop_names

def bulk_extract_crops(path_to_db_export, path_to_gsv_scrapes, destination_dir, mark_label=False):
    t_start = perf_counter()
    # create reader to read input csv with pano info
    csv_file = open(path_to_db_export)
    csv_f = csv.reader(csv_file)
    label_list = list(csv_f)
    row_count = len(label_list)

    # make the output directory if needed
    if not os.path.isdir(destination_dir):
        os.makedirs(destination_dir)

    with mp.Manager() as manager:
        # get cpu core count
        cpu_count = mp.cpu_count()

        # Create interprocess list to store output csv rows.
        output_rows = manager.list()

        lock = mp.Lock()

        # split label csv into chunks for multiprocessing
        # 1-index to ignore header row
        i = 1
        processes = []
        while i < row_count:
            chunk_size = (row_count - i) // cpu_count
            labels = list(islice(label_list, i, i + chunk_size))
            process = mp.Process(target=crop_label_subset, args=(labels, output_rows, path_to_gsv_scrapes, destination_dir, lock))
            processes.append(process)
            cpu_count -= 1
            i += chunk_size

        # start processes
        for p in processes:
            p.start()

        # join processes once finished
        for p in processes:
            p.join()

        # create writer to write output csv with crop info
        # TODO: for now, we will just have image_name point to a cropped jpg as model input 
        # and label_type as the output
        fields = ['image_name', 'label_type']
        csv_out = open(csv_crop_info, 'w')
        csv_w = csv.writer(csv_out)
        csv_w.writerow(fields)
        successful_crop_count = len(output_rows)
        # no_metadata_fail = 0
        # don't count header row as a failed crop
        no_pano_fail = ((row_count - 1) * MULTICROP_COUNT) - successful_crop_count

        for row in output_rows:
            csv_w.writerow(row)

        t_stop = perf_counter()
        execution_time = t_stop - t_start

        print("Finished Cropping.")
        print()
        
        return [row_count - 1, successful_crop_count, no_pano_fail, execution_time]

def crop_label_subset(input_rows, output_rows, path_to_gsv_scrapes, destination_dir, lock):
    counter = 0
    process_pid = os.getpid()
    for row in input_rows:
        counter += 1
        pano_id = row[0]
        sv_image_x = float(row[1])
        sv_image_y = float(row[2])
        label_type = int(row[3])
        photographer_heading = float(row[4])
        photographer_pitch = float(row[5])

        pano_img_path = os.path.join(path_to_gsv_scrapes, pano_id + ".jpg")

        pano_yaw_deg = 180 - photographer_heading

        # Extract the crop
        if os.path.exists(pano_img_path):
            crop_names = []
            if not label_type == 0:
                label_name = str(row[8])
                crop_names = make_crop(pano_img_path, sv_image_x, sv_image_y, pano_yaw_deg, photographer_pitch, destination_dir, label_name, lock, True)
            else:
                # In order to uniquely identify null crops, we concatenate the pid of process they
                # were generated on and the counter within the process to the name of the null crop.
                label_name = "null_" + str(process_pid) + "_" +  str(counter)
                crop_names = make_crop(pano_img_path, sv_image_x, sv_image_y, pano_yaw_deg, photographer_pitch, destination_dir, label_name, lock, False)

            for crop_name in crop_names:
                output_rows.append([crop_name, label_type])
        else:
            print("Panorama image not found.")
            try:
                logging.warning("Skipped label id " + label_name + " due to missing image.")
            except NameError:
                logging.warning("Skipped null crop " + str(process_pid) + " " + str(counter) + " due to missing image.")
