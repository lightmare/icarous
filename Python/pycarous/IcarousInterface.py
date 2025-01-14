import abc
import sys
import numpy as np

from ichelper import (LoadIcarousParams,
                      ReadFlightplanFile,
                      distance,
                      ConvertToLocalCoordinates,
                      ParseDaidalusConfiguration)
from CustomTypes import V2Vdata

class IcarousInterface(abc.ABC):
    """
    An abstract base class for interfacing with ICAROUS in python. Includes
    functions for inputting flight plan, geofence, and traffic information,
    and for recording log files. Subclasses must implement all of the
    functions marked @abc.abstractmethod.
    """
    def __init__(self, home_pos, callsign="SPEEDBIRD", vehicleID=0,
                 verbose=1, logRateHz=5):
        """
        Initialize Icarous interface
        :param home_pos: initial position / origin for local coordinates
        :param callsign: callsign for the vehicle
        :param vehicleID: unique integer ID for this Icarous instance
        :param verbose: control printout frequency (0: none, 1: some, 2+: more)
        :param logRateHz: number of data points to log per second
        """
        self.home_pos = home_pos
        self.callsign = callsign
        self.vehicleID = vehicleID
        self.verbose = verbose
        self.simType = ""

        self.defaultWPSpeed = 1
        self.windFrom = 0
        self.windSpeed = 0

        self.transmitter = None
        self.receiver = None

        # Aircraft data
        self.apps         = []
        self.params       = {}
        self.localMergeFixes = []
        self.plans        = []
        self.localPlans   = []
        self.fences       = []
        self.localFences  = []
        self.flightplan1  = []
        self.flightplan2  = []
        self.controlInput = [0.0, 0.0, 0.0]
        self.fenceList    = []
        self.mergeFixes   = []
        self.arrTime      = None
        self.trkband      = None
        self.gsband       = None
        self.altband      = None
        self.vsband       = None

        # Aircraft state
        self.currTime = 0
        self.position = self.home_pos
        self.velocity = [0.0, 0.0, 0.0]
        self.trkgsvs  = [0.0, 0.0, 0.0]
        self.localPos = [0.0, 0.0, 0.0]
        self.terminated = False
        self.running = False
        self.missionStarted = False
        self.missionComplete = False
        self.land = False

        # Vehicle logs
        self.ownshipLog = {
            "time": [],
            "position": [],
            "velocityNED": [],
            "commandedVelocityNED": [],
            "positionNED": [],
            "planOffsets":[],
            "trkbands": BandsLog(),
            "gsbands": BandsLog(),
            "altbands": BandsLog(),
            "vsbands": BandsLog(),
        }
        self.trafficLog = {}
        self.logRateHz = logRateHz
        self.minLogInterval = 1/self.logRateHz - 0.01
        self.planoffsets = [0,0,0,0,0,0]
        self.daaConfig = ""

    @abc.abstractmethod
    def SetPosUncertainty(self, xx, yy, zz, xy, yz, xz, coeff=0.8):
        """
        Set position uncertainty for vehicle model
        :param xx: x position variance [m^2] (East/West)
        :param yy: y position variance [m^2] (North/South)
        :param zz: z position variance [m^2] (Up/Down)
        :param xy: xy position covariance [m^2]
        :param yz: yz position covariance [m^2]
        :param xz: xz position covariance [m^2]
        :param coeff: smoothing factor used for uncertainty (default=0.8)
        """
        pass

    @abc.abstractmethod
    def SetVelUncertainty(self, xx, yy, zz, xy, yz, xz, coeff=0.8):
        """
        Set velocity uncertainty for vehicle model
        :param xx: x velocity variance [m^2] (East/West)
        :param yy: y velocity variance [m^2] (North/South)
        :param zz: z velocity variance [m^2] (Up/Down)
        :param xy: xy velocity covariance [m^2]
        :param yz: yz velocity covariance [m^2]
        :param xz: xz velocity covariance [m^2]
        :param coeff: smoothing factor used for uncertainty (default=0.8)
        """
        pass

    def InputWind(self, windFrom, windSpeed):
        """
        Set the current wind vector for vehicle simulation
        :param windFrom: wind source (deg CW, 0 is North)
        :param windSpeed: wind speed (m/s)
        """
        self.windFrom = windFrom
        self.windSpeed = windSpeed

    def ReceiveV2VData(self):
        """
        Receive any V2V messages available to receiver model and input to ICAROUS
        """
        if self.receiver is None:
            return
        if not self.missionStarted or self.missionComplete:
            return
        received_msgs = self.receiver.receive(self.currTime, self.position)
        for msg in received_msgs:
            self.InputV2VData(msg.data)

    def InputV2VData(self, data):
        """
        Input V2V data to ICAROUS
        :param data: V2VData to input
        """
        if data.type == "INTRUDER":
            self.InputTraffic(data.payload["callsign"], data.payload["pos"], data.payload["vel"])
        elif data.type == "MERGER":
            self.InputMergeData(data.payload)

    @abc.abstractmethod
    def InputTraffic(self, callsign, position, velocity):
        """
        Input traffic surveillance data to ICAROUS
        :param idx: callsign of the traffic vehicle
        :param position: traffic position [lat, lon, alt] (deg, deg, m)
        :param velocity: traffic velocity [vn, ve, vd] (m/s, m/s, m/s)
        """
        pass

    @abc.abstractmethod
    def InputFlightplan(self, fp, eta=False, repair=False):
        """
        Input a flight plan as a list of waypoints
        :param fp: a list of waypoints [lat, lon, alt, wp_metric]
        :param eta: when True, ICAROUS enforces wp arrival times, wp_metric (s)
                    when False, ICAROUS sets speed to each wp, wp_metric (m/s)
        :param repair: when True, repair linear flight plan to EUTL format
        """
        pass

    @abc.abstractmethod
    def InputFlightplanFromFile(self, filename, eta=False, repair=False,startTimeShift=0):
        """
        Input a flight plan from a MAVProxy formatted text file
        :param filename: path to the flight plan file
        :param scenarioTime: start time of the scenario (s)
        :param eta: when True, ICAROUS enforces wp arrival times, wp_metric (s)
                    when False, ICAROUS sets speed to each wp, wp_metric (m/s)
        :param repair: when True, repair linear flight plan to EUTL format
        """
        pass

    @abc.abstractmethod
    def InputGeofence(self, filename):
        """
        Input geofences from an xml file
        :param filename: path to xml geofence file
        """
        pass

    @abc.abstractmethod
    def InputMergeFixes(self, filename):
        """
        Input merge points from a MAVProxy formatted text file
        :param filename: path to the merge point file
        """
        pass

    @abc.abstractmethod
    def SetParameters(self, params):
        """
        Input ICAROUS parameters from a dictionary
        :param params: dict of params, PARAM_NAME -> PARAM_VALUE
        """
        pass

    def SetParametersFromFile(self, filename):
        """
        Input ICAROUS parameters from a .parm text file
        :param filename: path to .parm parameter file
        """
        params = LoadIcarousParams(filename)
        self.SetParameters(params)

    @abc.abstractmethod
    def InputMergeData(self, logs, delay):
        """
        Input V2V merge coordination data
        :param logs: merging log data
        :param delay: latency time to wait before processing logs (s)
        """
        pass

    @abc.abstractmethod
    def CheckMissionComplete(self):
        """ Return True if the mission is complete """
        pass

    def ConvertToLocalCoordinates(self, pos):
        return ConvertToLocalCoordinates(self.home_pos, pos)

    def ConvertLogsToLocalCoordinates(self, origin=None):
        """
        Convert all logs to local coordinates with origin at home_pos
        :param origin: origin for local coordinates - if None, use home position
        """
        origin = origin or self.home_pos
        self.home_pos = origin
        to_local = self.ConvertToLocalCoordinates
        posNED = list(map(to_local, self.ownshipLog["position"]))
        self.ownshipLog["positionNED"] = posNED
        for tfid in self.trafficLog.keys():
            tfPosNED = list(map(to_local, self.trafficLog[tfid]["position"]))
            self.trafficLog[tfid]["positionNED"] = tfPosNED
        self.localPlans = []
        self.localFences = []
        self.localMergeFixes = []
        for plan in self.plans:
            wps = [[wp.latitude,wp.longitude,wp.altitude] for wp in plan]
            times = [wp.time for wp in plan]
            tcps = [[*wp.tcp] for wp in plan]
            tcpValues = [[*wp.tcpValue] for wp in plan]
            localwps = list(map(to_local,wps))
            localFP = [[val[0],*val[1],*val[2],*val[3]] for val in zip(times,localwps,tcps,tcpValues)]
            self.localPlans.append(localFP)
        for fence in self.fences:
            localFence = list(map(to_local, fence))
            self.localFences.append(localFence)
        self.localMergeFixes = list(map(to_local, self.mergeFixes))

    def GetLocalFlightPlan(self, fp):
        local = []
        for wp in fp:
            if type(wp) == list:
                pt = wp
            else:
                pt = [wp.latitude,wp.longitude,wp.altitude]
            
            tcps = [wp.tcp[0],wp.tcp[1],wp.tcp[2]]
            tcpValues = [wp.tcpValue[0],wp.tcpValue[1],wp.tcpValue[2]]
            local.append([wp.time,*self.ConvertToLocalCoordinates(pt),*tcps,*tcpValues])
        return local

    def RecordOwnship(self):
        if self.ownshipLog["time"]:
            last_time = self.ownshipLog["time"][-1]
        else:
            last_time = -1
        if self.currTime - last_time < self.minLogInterval:
            return
        if sum(abs(p) for p in self.position) < 1e-3:
            return

        self.ownshipLog["time"].append(self.currTime)
        self.ownshipLog["position"].append(self.position)
        self.ownshipLog["velocityNED"].append(self.velocity)
        self.ownshipLog["positionNED"].append(self.localPos)
        self.ownshipLog["commandedVelocityNED"].append(self.controlInput)
        self.ownshipLog["planOffsets"].append(self.planoffsets)

        record_bands(self.ownshipLog["trkbands"], self.trkband)
        record_bands(self.ownshipLog["gsbands"], self.gsband)
        record_bands(self.ownshipLog["altbands"], self.altband)
        record_bands(self.ownshipLog["vsbands"], self.vsband)

    def RecordTraffic(self, callsign, position, velocity, localPos):
        if callsign not in self.trafficLog.keys():
            self.trafficLog[callsign] = {"time": [],
                                          "position": [],
                                          "velocityNED": [],
                                          "positionNED": []}
            last_time = -1
        else:
            last_time = self.trafficLog[callsign]["time"][-1]
        if self.currTime - last_time < self.minLogInterval:
            return
        self.trafficLog[callsign]["time"].append(self.currTime)
        self.trafficLog[callsign]["position"].append(list(position))
        self.trafficLog[callsign]["velocityNED"].append(velocity)
        self.trafficLog[callsign]["positionNED"].append(localPos)

    def TransmitPosition(self):
        """ Transmit current position """
        # Do not broadcast if running SBN
        if "SBN" in self.apps:
            return
        if self.transmitter is None:
            return
        if not self.missionStarted or self.missionComplete:
            return
        msg_data = {
            "callsign": self.callsign,
            "pos": self.position,
            "vel": self.velocity,
        }
        msg = V2Vdata("INTRUDER", msg_data)
        self.transmitter.transmit(self.currTime, self.position, msg)

    @abc.abstractmethod
    def Run(self):
        """ Run one timestep of the simulation """
        pass

    @abc.abstractmethod
    def StartMission(self):
        """ Send MissionStart command to ICAROUS """
        pass

    @abc.abstractmethod
    def Terminate(self):
        """ End any processes if necessary """
        pass

    def WriteLog(self, logname=""):
        """
        Save log data to a json file
        :param logname: name for the log file, default is simlog-[callsign].json
        """
        if logname == "":
            logname = "log/simlog-%s.json" % self.callsign
        if self.verbose > 0:
            print("writing log: %s" % logname)

        plans = []
        for plan in self.plans:
            wps = [[wp.time,wp.latitude,wp.longitude,wp.altitude,*wp.tcp,*wp.tcpValue]\
                   for wp in plan]
            plans.append(wps)

        geofences_local = [fence.copy() for fence in self.fenceList]
        for fence, vertices in zip(geofences_local, self.localFences):
            fence["vertices"] = vertices

        # Extract some daa parameters so they can be used for analysis
        if self.daaConfig:
            daaparams = ParseDaidalusConfiguration(self.daaConfig)
            m2ft = 3.28084

            correctiveRegion = daaparams['corrective_region'][1]
            alerterFound = False
            alerterList = daaparams['alerters'][1].split(',')
            alerterCorrective = ''
            detector = ''
            for alerter in alerterList:
                count = 1
                while alerterCorrective == '':
                    alerter = alerter.lower()
                    if daaparams[alerter+'_alert_'+str(count)+'_region'][1] == correctiveRegion:
                        alerterCorrective = alerter
                        detector = daaparams[alerter+'_alert_'+str(count)+'_detector'][1]
                        break
                    else:
                        count += 1
                if alerterCorrective != '':
                    break

            self.params["DET_1_WCV_DTHR"]=daaparams[alerterCorrective+'_'+detector+'_wcv_dthr'][0]*m2ft
            self.params["DET_1_WCV_ZTHR"]=daaparams[alerterCorrective+'_'+detector+'_wcv_zthr'][0]*m2ft
            self.params["DET_1_WCV_TCOA"] = daaparams[alerterCorrective+'_'+detector+'_wcv_tcoa'][0]*m2ft
            self.params["DET_1_WCV_TTHR"] = daaparams[alerterCorrective+'_'+detector+'_wcv_tthr'][0]*m2ft
            self.params["AL_1_ALERT_T"] = daaparams[alerterCorrective+'_alert_'+str(count)+'_alerting_time'][0]
            self.params["HORIZONTAL_NMAC"] = daaparams['horizontal_nmac'][0]*m2ft
            self.params["VERTICAL_NMAC"] = daaparams['vertical_nmac'][0]*m2ft

        log_data = {"state": self.ownshipLog,
                    "callsign": self.callsign,
                    "traffic": self.trafficLog,
                    "origin": self.home_pos,
                    "flightplans": plans,
                    "flightplans_local": self.localPlans,
                    "geofences": self.fenceList,
                    "geofences_local": geofences_local,
                    "mergefixes_local": self.localMergeFixes,
                    "parameters": self.params,
                    "sim_type": self.simType}

        import json
        with open(logname, 'w') as f:
            json.dump(log_data, f)


def BandsLog():
    return {
        "conflict": [],
        "resUp": [],
        "resDown": [],
        "numBands": [],
        "bandTypes": [],
        "low": [],
        "high": [],
    }


def record_bands(log, bands):
    filterinfnan = lambda x: "nan" if np.isnan(x)  else "inf" if np.isinf(x) else x
    if bands is not None:
        log["conflict"].append(bands['currentConflictBand'])
        log["resUp"].append(filterinfnan(bands['resUp']))
        log["resDown"].append(filterinfnan(bands['resDown'])) 
        log["numBands"].append(bands['numBands'])
        log["bandTypes"].append([bands['type'][i] for i in range(bands['numBands'])])
        log["low"].append([bands['min'][i] for i in range(bands['numBands'])])
        log["high"].append([bands['max'][i] for i in range(bands['numBands'])])
    else:
        log["conflict"].append(0)
        log["resUp"].append("nan")
        log["resDown"].append("nan")
        log["numBands"].append(0)
        log["bandTypes"].append([])
        log["low"].append([])
        log["high"].append([])
