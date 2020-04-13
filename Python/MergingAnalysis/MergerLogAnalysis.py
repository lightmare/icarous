import numpy as np
import math
import os
from matplotlib import pyplot as plt
from scipy.interpolate import interp1d
import itertools
import pandas as pd


RADIUS_OF_EARTH = 6378100.0


class MergerData:
    def __init__(self, v_id, merge_id=1, group="test"):
        self.id = v_id
        self.merge_id = merge_id
        self.group = group
        self.t = []
        self.state = {"t": [],
                      "intID": [],
                      "dist2int": [],
                      "speed": [],
                      "nodeRole": [],
                      "earlyArrTime": [],
                      "currArrTime": [],
                      "lateArrTime": [],
                      "zone": [],
                      "numSch": [],
                      "mergeSpeed": [],
                      "commandedSpeed": [],
                      "mergeDev": [],
                      "mergingStatus": [],
                      "lat": [],
                      "lon": [],
                      "alt": []}
        self.current_role = None
        self.role_changes = []
        self.metrics = {}

    def get(self, x, t=None):
        """Return the value of state[x] at time t"""
        if t is None:
            t = self.t
        return interp1d(self.state["t"], self.state[x], axis=0,
                        bounds_error=False, fill_value=None)(t)


def ReadMergerAppData(filename, vehicle_id, merge_id=1, group="test"):
    with open(filename, 'r') as fp:
        fp.readline()
        data_string = fp.readlines()

    data = MergerData(vehicle_id, merge_id=merge_id, group=group)
    data.output_dir = os.path.dirname(filename)
    for line in data_string:
        line = line.rstrip('\n')
        entries = line.split(',')
        intID = int(entries[1])
        if intID != merge_id:
            continue
        t = float(entries[0])
        data.t.append(t)
        data.state["t"].append(t)
        data.state["intID"].append(int(entries[1]))
        data.state["dist2int"].append(float(entries[2]))
        data.state["speed"].append(float(entries[3]))
        data.state["nodeRole"].append(int(entries[4]))
        data.state["earlyArrTime"].append(int(entries[5].lstrip().lstrip('(')))
        data.state["currArrTime"].append(int(entries[6]))
        data.state["lateArrTime"].append(int(entries[7].lstrip().rstrip(')')))
        data.state["zone"].append(int(entries[8]))
        data.state["numSch"].append(int(entries[9]))
        data.state["mergeSpeed"].append(float(entries[10]))
        data.state["commandedSpeed"].append(float(entries[11]))
        data.state["mergeDev"].append(float(entries[12]))
        data.state["mergingStatus"].append(int(entries[13]))
        data.state["lat"].append(float(entries[14]))
        data.state["lon"].append(float(entries[15]))
        data.state["alt"].append(float(entries[16]))

        role = int(entries[4])
        if data.current_role is not None:
            data.role_changes[-1][2] = t
        if role != data.current_role:
            data.role_changes.append([role, t, None])
        data.current_role = role

    return data


def compute_metrics(vehicles, plot=False, save=False):
    for v in vehicles:
        zone = v.get("zone")
        status = v.get("mergingStatus")
        v.metrics["group"] = v.group
        v.metrics["merge_id"] = v.merge_id
        v.metrics["vehicle_id"] = v.id
        v.metrics["coord_time"] = next(v.t[i] for i in range(len(v.t)) if zone[i] == 1)
        v.metrics["sched_time"] = next(v.t[i] for i in range(len(v.t)) if zone[i] == 2)
        v.metrics["entry_time"] = next(v.t[i] for i in range(len(v.t)) if zone[i] == 3)
        v.metrics["handoff_time"] = next(v.t[i] for i in range(len(v.t)) if status[i] == 1)
        v.metrics["sched_arr_time"] = v.get("currArrTime")[-1]
        v.metrics["actual_arr_time"] = v.t[-1]
        v.metrics["initial_speed"] = v.get("speed", v.metrics["sched_time"])
        v.metrics["merge_speed"] = v.get("mergeSpeed", v.metrics["entry_time"])
        v.metrics["actual_speed_to_handoff"] = average_speed(v, v.metrics["entry_time"],
                                                             v.metrics["handoff_time"])
        v.metrics["actual_speed_to_merge"] = average_speed(v, v.metrics["entry_time"],
                                                           v.metrics["actual_arr_time"])

    if plot:
        plt.figure()
        for v in vehicles:
            plt.plot(v.t, v.get("dist2int"), label="vehicle"+str(v.id))
        for v in vehicles:
            plt.plot(v.metrics["coord_time"],
                     v.get("dist2int", v.metrics["coord_time"]), '*')
            plt.plot(v.metrics["sched_time"],
                     v.get("dist2int", v.metrics["sched_time"]), '*')
            plt.plot(v.metrics["entry_time"],
                     v.get("dist2int", v.metrics["entry_time"]), '*')
            plt.plot(v.metrics["handoff_time"],
                     v.get("dist2int", v.metrics["handoff_time"]), 'r*')
            plt.plot(v.metrics["actual_arr_time"],
                     v.get("dist2int", v.metrics["actual_arr_time"]), 'b*')
            plt.plot(v.metrics["sched_arr_time"], 0, 'g*')
        plt.title("Merging Operation Summary")
        plt.plot([], [], 'r*', label="merger app gives back control")
        plt.plot([], [], 'g*', label="scheduled arrival time")
        plt.plot([], [], 'b*', label="actual arrival time")
        plt.xlabel("time (s)")
        plt.ylabel("distance to merge point (m)")
        plt.legend()
        plt.grid()
        if save:
            plt.savefig(os.path.join(v.output_dir, "summary"))


def write_metrics(vehicles):
    """ Add vehicle metrics to a csv table """
    filename = "MergingData.csv"
    if os.path.isfile(filename):
        table = pd.read_csv(filename, index_col=0)
    else:
        table = pd.DataFrame({})
    for v in vehicles:
        index = v.group+"_"+str(v.merge_id)+"_"+str(v.id)
        metrics = pd.DataFrame(v.metrics, index=[index])
        table = table.combine_first(metrics)
    table = table[v.metrics.keys()]
    table.to_csv(filename)


def average_speed(vehicle, t1, t2):
    dX = vehicle.get("dist2int", t1) - vehicle.get("dist2int", t2)
    dT = t2 - t1
    return abs(dX/dT)


def gps_distance(lat1, lon1, lat2, lon2):
    '''return distance between two points in meters,
    coordinates are in degrees
    thanks to http://www.movable-type.co.uk/scripts/latlong.html'''
    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)
    lon1 = math.radians(lon1)
    lon2 = math.radians(lon2)
    dLat = lat2 - lat1
    dLon = lon2 - lon1

    a = math.sin(0.5*dLat)**2 + math.sin(0.5*dLon)**2 * math.cos(lat1) * math.cos(lat2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0-a))
    return RADIUS_OF_EARTH * c


def plot(vehicles, field, save=False):
    plt.figure()
    for v in vehicles:
        plt.plot(v.t, v.get(field), label="vehicle"+str(v.id))
    plt.title(field)
    plt.xlabel("time (s)")
    plt.ylabel(field)
    plt.legend()
    plt.grid()
    if save:
        plt.savefig(os.path.join(v.output_dir, field))


def plot_separation(vehicles, save=False):
    plt.figure()
    for v1, v2 in itertools.combinations(vehicles, 2):
        time_range = v1.t
        lat1 = v1.get("lat", time_range)
        lon1 = v1.get("lon", time_range)
        lat2 = v2.get("lat", time_range)
        lon2 = v2.get("lon", time_range)
        dist = [gps_distance(la1, lo1, la2, lo2) for la1,lo1,la2,lo2 in
                zip(lat1,lon1,lat2,lon2)]
        plt.plot(time_range, dist, label="vehicle"+str(v1.id)+" to vehicle"+str(v2.id))
    plt.legend()
    plt.grid()
    plt.ylim((0, plt.ylim()[1]))
    if save:
        plt.savefig(os.path.join(v1.output_dir, "dist"))


def plot_speed(vehicles, save=False):
    for v in vehicles:
        plt.figure()
        line1, = plt.plot(v.t, v.get("speed"))
        line2, = plt.plot(v.t, v.get("mergeSpeed"), '--')
        line3, = plt.plot(v.t, v.get("commandedSpeed"), '-.')
        line1.set_label("vehicle"+str(v.id)+" actual speed")
        line2.set_label("vehicle"+str(v.id)+" merge speed")
        line3.set_label("vehicle"+str(v.id)+" commanded speed")
        plt.xlabel('time (s)')
        plt.ylabel('speed (m/s)')
        plt.legend()
        if save:
            plt.savefig(os.path.join(v.output_dir, "speed_"+str(v.id)))


def plot_roles(vehicles, save=False):
    plt.figure()
    plt.title("Raft Node Roles")
    colors = ['y', 'r', 'b', 'g']
    labels = ["NEUTRAL", "FOLLOWER", "CANDIDATE", "LEADER"]
    for v in vehicles:
        for rc in v.role_changes:
            role, t0, tEnd = rc
            plt.plot([t0, tEnd], [v.id, v.id], '-', c = colors[role],
                     linewidth=20.0, solid_capstyle="butt")
    for c, l in zip(colors, labels):
        plt.plot([], [], 's', color=c, label=l)
    vids = [v.id for v in vehicles]
    vnames = ["vehicle"+str(v.id) for v in vehicles]
    plt.yticks(vids, vnames)
    plt.ylim([min(vids) - 1, max(vids) + 1])
    plt.xlabel("Time (s)")
    plt.legend()
    plt.grid()
    if save:
        plt.savefig(os.path.join(v.output_dir, "roles"))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Validate Icarous simulation data")
    parser.add_argument("data_location", help="directory where log files are")
    parser.add_argument("--merge_id", default=1, type=int, help="merge point id to analyze")
    parser.add_argument("--num_vehicles", default=10, type=int, help="number of vehicles")
    parser.add_argument("--plot", action="store_true", help="plot the scenario")
    parser.add_argument("--save", action="store_true", help="save the results")
    args = parser.parse_args()

    # Read merger log data
    vehicles = []
    group = args.data_location.strip("/").split("/")[-1]
    for i in range(args.num_vehicles):
        filename = "merger_appdata_" + str(i) + ".txt"
        filename = os.path.join(args.data_location, filename)
        if not os.path.isfile(filename):
            break
        data = ReadMergerAppData(filename, vehicle_id=i, merge_id=args.merge_id, group=group)
        vehicles.append(data)

    # Generate plots
    if args.plot:
        plot(vehicles, "dist2int", save=args.save)
        plot_roles(vehicles, save=args.save)
        plot_speed(vehicles, save=args.save)
        plot_separation(vehicles, save=args.save)
        plt.show()

    # Compute metrics
    compute_metrics(vehicles, plot=args.plot, save=args.save)
    write_metrics(vehicles)
