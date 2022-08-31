#!/usr/bin/env python3
import netmiko
import copy
import datetime
import difflib
import diffios
import telnetlib
import requests
import time
import json
import sys
import os
import re
import xlrd2
import csv

__ROW_CONTEXT_NUM__MAX__ = 5
__ROW_CONTEXT_NUM__MIN__ = 3

#
# Ignore string used by diffios to ignore some unimportant configuration
# Path point to Device information csv file 
# CORP_ID represent WeChatCooperation ID
# Secret represent WeChatApplication Secret 
#


Ignore_cisco_ios = """Building configuration...
Current configuration
Last configuration change
NVRAM config last updated
---- More (q/Q to quit) ----
exit

"""
Path = "Device.csv"
CORP_ID = "wxdd89b0afd049ca22"
SECRET = "P2SohYCm9mZFO4gZ2aTxZz1Ace6pgPgP655T5qq2JTo"


class NetWork_Connect:
    """
    For various network products, considering by configure difference of connnet method(ex ssh\telnet), 
    connect device through difference method.

    Cisco ios devices, most of them support telnet connect and a litle of them can be connected by ssh.
    Arista os, because there is only one device and also can only connect by telnet. 
    ZyXEL os decvices, netmiko donot provide telnet connect method, so while connect failed ,try to 
        examine devices ssh configuration.
    MyPower os devices, netmiko donot provide any connect method, but through tryying zte_os was obvious samiliar.
    Oring os devices, netmiko donot provide any connect method as well, so we use telnetlib to connect device.
    Rubytech os devices connect method same as Oring.

    For every device in NetWork_Connect, we do things in privilege:
        1. Connect through SSH or Telnet;
        2. Send command to get device configuration;
        3. Get hostname from device configuration through RE;
        4. Consolidate date include device host, device hostname, device configuratuin.
    """

    #
    #Get configuration from  Cisco Device
    #Connect methods: Netmiko telnet &  ssh(depend on device["device_tyoe"]) 
    #Data request: Network_Connect.self, device{"host","user","passward","secret","device_type"}
    #Data return: Config_Data = [running_configuration, hostname,ip]
    #
    def getConfig_Cisco(self,device):
        device["conn_timeout"] = 20
        with netmiko.ConnectHandler(**device) as net_connect:
            if device["secret"] != "":
                net_connect.enable()
            runnning_config = net_connect.send_command("show running-config")
            version = net_connect.send_command("show version",use_textfsm=True)[0]
        hostname = version['hostname']
        ip = device["host"]
        Config_Data = [runnning_config,hostname,ip]
        return Config_Data

    #
    #Get configuration from  ZyXEL Device
    #Connect methods: Netmiko ssh (Connect Error maybe caused by device ssh configuration ) 
    #Data request: Network_Connect.self, device{"host","user","passward","secret","device_type"}
    #Data return: Config_Data = [running_configuration, hostname,ip]
    #
    def getConfig_Zyxel(self,device):
        device["conn_timeout"] = 20
        #device["timeout"] = 120
        with netmiko.ConnectHandler(**device) as net_connect:
            runnning_config = net_connect.send_command("show running-config")
            system_information = net_connect.send_command("show system-information")
        hostname = re.findall(r"SystemName:(.*?)\n",system_information.replace(' ','').replace("7","").replace("\t",""))[0]
        ip = device["host"]
        runnning_config = runnning_config.replace("7","")
        Config_Data = [runnning_config,hostname,ip]
        return Config_Data

    #
    #Get configuration from  Mypower Device
    #Connect methods: Netmiko telnet (Use zte_zxros just for connect. There are many similarities between the two systems) 
    #Data request: Network_Connect.self, device{"host","user","passward","secret","device_type"}
    #Data return: Config_Data = [running_configuration, hostname,ip]
    #
    def getConfig_MyPower(self,device):
        device["conn_timeout"] = 20
        #device["timeout"] = 120
        with netmiko.ConnectHandler(**device) as net_connect:
            if device["secret"] != "":
                net_connect.enable()
            runnning_config = net_connect.send_command_timing("show running-config")
            if "---MORE---" in runnning_config:
                runnning_config+= net_connect.send_command_timing('                         ',strip_prompt=False, strip_command=False, normalize=False)
            prompt = net_connect.find_prompt()
        hostname = re.findall(r"hostname (.*?)\n",runnning_config)[0]
        ip = device["host"]
        runnning_config = runnning_config.replace("---MORE---","").replace(prompt,"")
        Config_Data = [runnning_config,hostname,ip]
        return Config_Data

    #
    #Get configuration from Oring Device
    #Connect methods: Telnetlib telnet 
    #Data request: Network_Connect.self, device{"host","user","passward","secret","device_type"}
    #Data return: Config_Data = [running_configuration, hostname,ip]
    #
    def getConfig_Oring(self,device):
        tn = telnetlib.Telnet(device['host'], port=23)
        tn.read_until(b"Username :")
        tn.write(device["username"].encode("gbk")+b'\r\n')
        tn.read_until(b"Password :")
        tn.write(device["password"].encode("gbk")+b'\r\n')
        tn.read_until(b"switch>")
        tn.write(b'show config\r\n')
        tn.write(b'\r\n\r\n\r\n\r\n\r\n\r\n\r\n\r\n\r\n\r\n')
        tn.write(b'\r\n\r\n\r\n\r\n\r\n\r\n\r\n\r\n\r\n\r\n')
        tn.write(b'\r\n\r\n\r\n\r\n\r\n\r\n\r\n\r\n\r\n\r\n')
        tn.write(b'\r\n\r\n\r\n\r\n\r\n\r\n\r\n\r\n\r\n\r\n')
        tn.write(b'\r\n\r\n\r\n\r\n\r\n\r\n\r\n\r\n\r\n\r\n')
        runnning_config = tn.read_until(b"switch>").decode("gbk")
        hostname = re.findall(r"Name:(.*?)\n",runnning_config.replace(" ",'').replace("\r",""))[0]
        ip = device["host"]
        runnning_config = runnning_config.replace("---- More (q/Q to quit) ----","").replace("\n","@@")
        trush = re.findall(r"Interface Statistics(.*)VLAN Configuration",runnning_config)[0]
        runnning_config = runnning_config.replace(trush,"").replace("@@","\n")
        Config_Data = [runnning_config,hostname,ip]
        return Config_Data

    #
    #Get configuration from Rubytech Device
    #Connect methods: Telnetlib telnet (Rubytech device cannot use command "show running-config", 
    #                 so we collect several show command and use re to compose them ) 
    #Data request: Network_Connect.self, device{"host","user","passward","secret","device_type"}
    #Data return: Config_Data = [running_configuration, hostname,ip]
    #
    def getConfig_Rubytech(self,device):
        tn = telnetlib.Telnet(device['host'], port=23)
        tn.read_until(b"Login:")
        tn.write(device["username"].encode("gbk")+b'\n')
        tn.read_until(b"Password:")
        tn.write(b'admin\n')
        hostname = re.findall("\r\n(.*?)#",tn.read_until(b"#").decode("gbk"))[0]
        prompt =hostname+ "#"
        running_config = ""
        #Get ip config
        NetWork_Connect.rubytech_enterMode(tn,"ip")
        tn.write(b"show\n")
        show_ip = tn.read_until(b"#").decode("gbk").replace("\n","@@")
        running_config = NetWork_Connect.rubytech_re(hostname,show_ip,running_config,"ip")
        NetWork_Connect.rubytech_exit(tn)
        #Get stp
        NetWork_Connect.rubytech_enterMode(tn,"stp")
        tn.write(b"show config\n")
        show_stp = tn.read_until(b"#").decode("gbk").replace("\n","@@")
        running_config = NetWork_Connect.rubytech_re(hostname,show_stp,running_config,"stp")
        NetWork_Connect.rubytech_exit(tn)
        #Get trunk
        NetWork_Connect.rubytech_enterMode(tn,"trunk")
        tn.write(b"show aggtr-view\n")
        tn.write(b'         ')
        show_aggtr = tn.read_until(b"#").decode("gbk").replace("\n","@@").replace("...(q to quit)","")
        running_config = NetWork_Connect.rubytech_re(hostname,show_aggtr,running_config,"trunk")
        tn.write(b"show lacp-config\n")
        show_lacp = tn.read_until(b"#").decode("gbk").replace("\n","@@")
        running_config = NetWork_Connect.rubytech_re(hostname,show_lacp,running_config,"trunk")
        NetWork_Connect.rubytech_exit(tn)
        ##Get Vlan
        NetWork_Connect.rubytech_enterMode(tn,"vlan")
        tn.write(b"show conf\n")
        show_vlan_conf = tn.read_until(b"#").decode("gbk").replace("\n","@@")
        running_config = NetWork_Connect.rubytech_re(hostname,show_vlan_conf,running_config,"vlan")
        tn.write(b"show group\n")
        show_vlan_group = tn.read_until(b"#").decode("gbk").replace("\n","@@")
        running_config = NetWork_Connect.rubytech_re(hostname,show_vlan_group,running_config,"vlan")
        tn.write(b"show mgt-vlan\n")
        show_vlan_mgt = tn.read_until(b"#").decode("gbk").replace("\n","@@")
        running_config = NetWork_Connect.rubytech_re(hostname,show_vlan_mgt,running_config,"vlan")
        tn.write(b"show pvid\n")
        show_vlan_pvid = tn.read_until(b"#").decode("gbk").replace("\n","@@")
        running_config = NetWork_Connect.rubytech_re(hostname,show_vlan_pvid,running_config,"vlan")
        NetWork_Connect.rubytech_exit(tn)
        #Get port
        NetWork_Connect.rubytech_enterMode(tn,"port")
        tn.write(b"show conf\n")
        show_port_conf = tn.read_until(b"#").decode("gbk").replace("\n","@@")
        running_config = NetWork_Connect.rubytech_re(hostname,show_port_conf,running_config,"port")
        NetWork_Connect.rubytech_exit(tn)
        #Get Qos
        NetWork_Connect.rubytech_enterMode(tn,"qos")
        tn.write(b"show port\n")
        show_qos_port = tn.read_until(b"#").decode("gbk").replace("\n","@@")
        running_config = NetWork_Connect.rubytech_re(hostname,show_qos_port,running_config,"qos")
        NetWork_Connect.rubytech_exit(tn)
        #Get Security
        NetWork_Connect.rubytech_enterMode(tn,"security")
        NetWork_Connect.rubytech_enterMode(tn,"isolated-group")
        tn.write(b"show\n")
        show_isolated_group = tn.read_until(b"#").decode("gbk").replace("\n","@@")
        running_config = NetWork_Connect.rubytech_re(hostname,show_isolated_group,running_config,"security-isolated-group")
        NetWork_Connect.rubytech_exit(tn)
        NetWork_Connect.rubytech_enterMode(tn,"mirror")
        tn.write(b"show\n")
        show_mirror = tn.read_until(b"#").decode("gbk").replace("\n","@@")
        running_config = NetWork_Connect.rubytech_re(hostname,show_mirror,running_config,"security-mirror")
        NetWork_Connect.rubytech_exit(tn)
        NetWork_Connect.rubytech_exit(tn)
        #Get System
        NetWork_Connect.rubytech_enterMode(tn,"system")
        tn.write(b"show\n")
        show_system = tn.read_until(b"#").decode("gbk").replace("\n","@@")
        running_config = NetWork_Connect.rubytech_re(hostname,show_system,running_config,"system")
        NetWork_Connect.rubytech_exit(tn)
        #Get Snmp
        NetWork_Connect.rubytech_enterMode(tn,"snmp")
        tn.write(b"show\n")
        show_snmp = tn.read_until(b"#").decode("gbk").replace("\n","@@")
        running_config = NetWork_Connect.rubytech_re(hostname,show_snmp,running_config,"snmp")
        NetWork_Connect.rubytech_exit(tn)
        #Get mac-table
        NetWork_Connect.rubytech_enterMode(tn,"mac-table")
        NetWork_Connect.rubytech_enterMode(tn,"port-security")
        tn.write(b"show\n")
        tn.write(b" ")
        show_port_security= tn.read_until(b"#").decode("gbk").replace("\n","@@").replace("...(q to quit)","")
        running_config = NetWork_Connect.rubytech_re(hostname,show_port_security,running_config,"mac-table-port-security")
        NetWork_Connect.rubytech_exit(tn)
        NetWork_Connect.rubytech_enterMode(tn,"static-mac")
        tn.write(b"show\n")
        show_static_mac= tn.read_until(b"#").decode("gbk").replace("\n","@@")
        running_config = NetWork_Connect.rubytech_re(hostname,show_static_mac,running_config,"mac-table-static-mac")
        NetWork_Connect.rubytech_exit(tn)
        NetWork_Connect.rubytech_exit(tn)
        #Get manament
        NetWork_Connect.rubytech_enterMode(tn,"management")
        tn.write(b"show\n")
        show_management = tn.read_until(b"#").decode("gbk").replace("\n","@@")
        running_config = NetWork_Connect.rubytech_re(hostname,show_management,running_config,"management")
        NetWork_Connect.rubytech_exit(tn)
        tn.close()
        Config_Data = [running_config,hostname,device["host"]]
        return Config_Data
    
    #
    #Get configuration from Arista Device
    #Connect methods: Netmiko ssh (There is only one Arista device and can be connect by ssh only) 
    #Data request: Network_Connect.self, device{"host","user","passward","secret","device_type"}
    #Data return: Config_Data = [running_configuration, hostname,ip]
    #
    def getConfig_Arista(self,device):
        device["conn_timeout"] = 15
        #device["timeout"] = 120
        with netmiko.ConnectHandler(**device) as net_connect:
            net_connect.enable()
            runnning_config = net_connect.send_command("show running-config")
        hostname = re.findall(r"hostname (.*?)\n",runnning_config)[0]
        ip = device["host"]
        Config_Data = [runnning_config,hostname,ip]
        return Config_Data

    #
    #Rubytech telnetlib telnet connect close
    #Data request: telnetlib open object
    #Data return: None
    #
    def rubytech_exit(tn):
        tn.write(b"exit\n")
        tn.read_until(b"#")
    
    #
    #Rubytech telnetlib telnet send mode command
    #Data request: telnetlib open object, command mode
    #Data return: None
    #
    def rubytech_enterMode(tn,ruby_mode):
        tn.write(ruby_mode.encode("gbk")+b'\n')
        tn.read_until(b"#")
    
    #
    #Rubytech re  compose runnning-config
    #Data request: Rubytech hostname, show conmmand response, runnning-config,show command mode
    #Data return: running-config
    #
    def rubytech_re(hostname,show_data,running_config,mode):
        data = re.findall(r"show(.*)"+hostname+"\("+mode+"\)#",show_data)[0].replace("@@","\n")
        running_config = running_config+data
        return running_config

class Config_diff:
    """
    Config_diff rely on diffios and difflib,and compare result output to three file "result.html", "result.csv" and "Change.txt"
    Device configuration data from two files analysis in this privilge:
    1. Read file date from two file paths;
    2. Compare two date through two methods;
    3. Output compare result to certain file.

    """
    
    #
    #Compare two txt file and write compare result to html file
    #Compare method: difflib
    #Data request: file1 path, file2 path, output file path
    #Data return: None
    #
    def compare_files_Html(file1, file2, output):
        file1_content = IOstream.Config_File_Read(file1).splitlines(keepends=True)
        file2_content = IOstream.Config_File_Read(file2).splitlines(keepends=True) 
        d = difflib.HtmlDiff()
        result = d.make_file(file1_content, file2_content)
        with open(output, 'w') as f:
            f.writelines(result)

    #
    #Compare two txt file and wtrite compare result to txt file
    #Compare method: difflib
    #Data request: file1 path, file2 path, output file path, difference ammount, device hostname, different device host list
    #Data return: difference amount, different device host list
    #
    def compare_files_Node(file1, file2, output, difference,hostname,Difference_device):
        file1_content = IOstream.Config_File_Read(file1).splitlines(keepends=True)
        file2_content = IOstream.Config_File_Read(file2).splitlines(keepends=True)
        cont1 = list(difflib.ndiff(file1_content,file2_content))
        dic_list = dict(enumerate(cont1))
        a = copy.deepcopy(dic_list)
        #print(a)
        for i in range(0,len(a)):
            if not re.match(r"([\+\-.*]|( \!))",a[i]):
                del(a[i])
        list1 = list(a.values())
        #print(list1)
        for i in list(a.keys()):
            if re.match(r". \!.*",a[i]):
                del(a[i])
                continue
            if re.match(r"  end.*",a[i]):
                del(a[i])
            if re.match(r"         *",a[i]):
                del(a[i])
        list2 = list(a.values())
        #print(list2)
        with open(output, 'w') as f:
            for i in list2:
                f.write(i)
        if len(list2):
            difference +=1
            Difference_device.append(hostname)
        return difference,Difference_device
    
    #
    #Compare two file and write compare result to csv file
    #Compare method: diffios (Lib for Cisco device)
    #Data request: file1 path, file2 path, ignore.txt path, output file path
    #Data return: None
    #
    def compare_file_diffios(file_base,file_dev,ignore,output):
        with open(output, 'a') as csvfile:
            csvwriter = csv.writer(csvfile, lineterminator='\n')
            # write the headers
            if not os.path.exists(output) :
                csvwriter.writerow(["Comparison", "Baseline", "Additional", "Missing"])
            #comparison_file = os.path.join(file_dev, f)
            # initialise the diffios Compare object
            diff = diffios.Compare(file_base, file_dev, ignore)
            csvwriter.writerow([
                os.path.basename(file_dev),
                os.path.basename(file_base),
                # write the formatted differences to the csv file
                diff.pprint_additional(),
                diff.pprint_missing()
            ])
    
    #
    #Compare device config file with baseline file and write difference to txt file 
    #Compare method: re
    #Data request: file1 path, file2 path, output file path, baseline_compare difference amount, 
    #              baseline_compare different device ip list, device hostname
    #Data return: baseline_compare difference amount, baseline_compare different device ip list
    #
    def baseline_compare(baseline_file_path,file_dev,output,Baseline_difference,Baseline_different_device,hostname):
        baseline_difference = ""
        file1_baseline_data = open(baseline_file_path,"r")
        file1_baseline = file1_baseline_data.readlines()
        file2_device_date = open(file_dev,"r")
        file2_device = file2_device_date.read()
        for line in file1_baseline:
            if file2_device.replace(line,"") == file2_device:
                baseline_difference += "-"+line+"\n"
        file1_baseline_data.close()
        file2_device_date.close()
        if baseline_difference == "":
            different_flag = False
        else:
            different_flag = True
            Baseline_difference += 1
            Baseline_different_device.append(hostname)
        with open(output,"w") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S",time.localtime())+"\n")
            f.write(baseline_difference)
        return Baseline_difference,Baseline_different_device
    


class IOstream:
    """
    File input and output stream deal part.
    In this part code make the file root for each device. Every device' s root 'has analysis' and 'config'
    two package, continues device daily configuration and configuaration anallysis result from comparation
    with baseline config and yestarday configuration.
    Also this part define methods read and output data to certain file.
    """
    
    def Get_Device_List(path):
        Device_List = []
        csvfile = open(path,encoding="utf-8-sig",mode="r")
        readfile = csv.DictReader(csvfile)
        for row in readfile:
            #print(row)
            Device_List.append(row)
        return Device_List

    def Config_File_Write(data,hostname,time,path):
        if not os.path.exists(path+"/"+"BaseLine "+hostname+".txt"):
            with open(path+"/"+"BaseLine "+hostname+".txt",'w',encoding="utf-8") as f:
                f.write(data)
        with open(path+"/"+time+" "+hostname+".txt",'w',encoding="utf-8") as f:
            f.write(data)

            Device_List.append(row)
        return Device_List

    def Config_File_Write(data,hostname,time,path):
        if not os.path.exists(path+"/"+"BaseLine "+hostname+".txt"):
            with open(path+"/"+"BaseLine "+hostname+".txt",'w',encoding="utf-8") as f:
                f.write(data)
        with open(path+"/"+time+" "+hostname+".txt",'w',encoding="utf-8") as f:
            f.write(data)

    def Config_File_Read(path):
        with open(path,'r') as f:
            data = f.read()
        if re.findall(r"password \d (.*)\n",data):
            data = data.replace(re.findall(r"password \d (.*)\n",data)[0],"")
        if re.findall(r"ntp clock-period (.*)\n",data):
            data = data.replace(re.findall(r"ntp clock-period (.*)\n",data)[0],"")
        if re.findall(r"System Up Time(.*)\n",data):
            data = data.replace(re.findall(r"System Up Time(.*)\n",data)[0],"")
        if re.findall(r"Current Time(.*)\n",data):
            data = data.replace(re.findall(r"Current Time(.*)\n",data)[0],"")
        return data

    def Create_Ignore_File(path,Ignore):
        with open(path,"w") as f:
            f.write(Ignore)

    #def Create_Config_Log(path,time,Backup_Device,Backup_Device_F,Error_Device,Compare_Device,Compare_Device_Diff,Difference_device,Baseline_difference,Baseline_different_device):
    def Create_Config_Log(path,time,Backup_Device,Backup_Device_F,Error_Device,Compare_Device,Compare_Device_Diff,Difference_device):
        log = ""
        if Backup_Device_F == 0:
            log += "All Config Backup Successfull!"+str(Backup_Device)+" Devices Backup!\n"
        else:
            log += "Config Backup Abnormal! "+str(Backup_Device)+" Devices Backup, "+str(Backup_Device_F)+" Devices Failed!\n\t"
            log += "Failed Host: \n\t"+str(', '.join(Error_Device))+"\n"
        '''
        if Baseline_difference == 0:
            log += "Baseline Compare No Difference! "+str(Compare_Device)+" Device Compared!\n\t"
        else:
            log += "Baseline Config Compare Abnormal! "+str(Compare_Device)+" Devices Compare, "+str(Baseline_difference)+" Devices Difference!\n   \t"
            log += "Difference Host: \n   \t\t"+str(', '.join(Baseline_different_device))+"\n"
        '''
        if Compare_Device_Diff == 0:
            log += "Config Compared No Difference! "+str(Compare_Device)+" Device Compared!\n"
        else:
            log += "Config Compared Abnormal! "+str(Compare_Device)+" Devices Compared, "+str(Compare_Device_Diff)+" Devices Difference!\n   \t"
            log += "Difference Host: \n   \t"+str(', '.join(Difference_device))+"\n"
        print(log)
        with open(path,"a") as f:
            f.write("{:=^70s}".format(time))
            f.write("\n"+log)
    
    def Create_Error_File(path,time,Error):
        with open(path,"a") as f:
            f.write("{:=^50s}".format(time))
            f.write("\n"+Error)
            f.write("\n")

    def Get_Device_Json(path_Json,path_Device):
        f = open(path_Json,"r",encoding="utf-8")
        data = json.load(f)
        device_list = []
        host_ip = ""
        password = ""
        secret = ""
        username = "admin"
        for host in data['zabbix_export']['hosts']:
            device_type = ''
            host_ip = host['interfaces'][0].get("ip",'no')  
            os_type = host['templates'][0]['name']
            if re.search(r"Cisco",os_type):
                device_type = 'cisco_ios_telnet'
                password = "chicony"
                secret = "Qw1.ccy"
            elif re.search(r"Oring",os_type):
                device_type = 'Oring_os'
            elif re.search(r"MyPower",os_type):
                device_type = 'zte_zxros_telnet'
            elif re.search(r"ZYXEL",os_type):
                device_type = 'zyxel_os'
            else:
                continue  
            device = [host_ip,username,password,secret,device_type]
            device_list.append(device)
        csvfile = open(path_Device,encoding="utf-8-sig",mode="w",newline="")
        header_list = ["host", "username", "password", "secret","device_type"]
        writer = csv.writer(csvfile)
        writer.writerow(header_list)
    
    def Create_Baseline_File(device_type,path,hostname):
        if re.match( r"cisco",device_type):
            shutil.copy("baseline/cisco-baseline.txt",path+"/"+"BaseLine "+hostname+".txt")
        elif re.match( r"zyxel",device_type):
            pass
        elif re.match( r"zte",device_type):
            pass
        elif re.match( r"Oring",device_type):
            pass
        elif re.match( r"ruby",device_type):
            pass
        

class Config_result:
    #
    #Config compare main method
    #
    def Record(Config_data,difference,Difference_device):
        path = os.path.dirname(os.path.abspath(__file__))
        path = path+"/"+Config_data[1]+" "+Config_data[2]
        if not os.path.exists(path) :
                os.mkdir(path)
        config_path = path+"/config"
        if not os.path.exists(config_path) :
                os.mkdir(config_path)
        IOstream.Config_File_Write(Config_data[0],Config_data[1],datetime.datetime.now().strftime('%Y-%m-%d'),config_path)
        file1 = config_path+"/"+(datetime.datetime.now()+datetime.timedelta(days=-1)).strftime('%Y-%m-%d')+" "+Config_data[1]+".txt"
        file2 = config_path+"/"+datetime.datetime.now().strftime('%Y-%m-%d')+" "+Config_data[1]+".txt"
        if not os.path.exists(file1):
            file1 = config_path+"/BaseLine "+Config_data[1]+".txt"
        analysis_path = path+"/analysis"
        if not os.path.exists(analysis_path) :
            os.mkdir(analysis_path)
        ignore_path = analysis_path + "/ignore.txt"
        IOstream.Create_Ignore_File(ignore_path,Ignore_cisco_ios)
        Config_diff.compare_file_diffios(file1,file2,ignore_path,analysis_path+'/result.csv')
        Config_diff.compare_files_Html(file1,file2 , analysis_path+'/result.html')
        difference,Difference_device = Config_diff.compare_files_Node(file1,file2 , analysis_path+'/Change.txt',difference,Config_data[2],Difference_device)
        return difference,Difference_device

class WeChatPub:
    s = requests.session()

    def __init__(self):
        self.token = self.get_token()

    def get_token(self):
        url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={CORP_ID}&corpsecret={SECRET}"
        rep = self.s.get(url)
        if rep.status_code != 200:
            print("request failed.")
            return
        return json.loads(rep.content)['access_token']

    #def make_msg(Error_Device,Device_List,Baseline_difference, Baseline_different_device,difference,Difference_device):
    def make_msg(Error_Device,Device_List,difference,Difference_device):
        if len(Error_Device):
            Backup_Inform = f"设备配置文件未完全备份"
            Backup_detail = f"共备份{len(Device_List)}台设备,{len(Error_Device)}台设备备份失败\n失败设备IP:\n{', '.join(Error_Device)}" 
        else:
            Backup_Inform = f"设备配置文件备份成功"
            Backup_detail = f"共备份{len(Device_List)}台设备,{len(Device_List)}台设备备份成功"
        '''
        if Baseline_difference == 0:
            Baseline_Config_Differ = f"设备安全基线配置检查完毕"
            Baseline_Config_Difference = f"共检查{len(Device_List)-len(Baseline_different_device)}台设备,配置文件均无差异"
        else:
            Baseline_Config_Differ = f"安全基线配置存在部分差异"
            Baseline_Config_Difference = f"共检查{len(Device_List)-len(Baseline_different_device)}台设备,{Baseline_difference}台设备存在差异\n差异设备IP：\n{', '.join(Baseline_different_device)}"
        '''
        if difference == 0:
            Config_Differ = f"设备配置文件差异检查完毕"
            Config_Difference = f"共检查{len(Device_List)-len(Error_Device)}台设备,配置文件均无差异"     
        else:  
            Config_Differ = f"配置文件对比存在部分差异" 
            Config_Difference = f"共检查{len(Device_List)-len(Error_Device)}台设备,{difference}台设备存在差异\n差异设备IP:\n{', '.join(Difference_device)}"
        timenow = time.strftime("%Y-%m-%d %H:%M:%S",time.localtime())
        content = f"<div class=\"gray\">{timenow}</div> <div class=\"normal\">{Backup_Inform}</div><div class=\"highlight\">{Backup_detail}</div>"\
                  f"<div class=\"normal\">{Config_Differ}</div><div class=\"highlight\">{Config_Difference}</div>" 
        '''
        content = f"<div class=\"gray\">{timenow}</div> <div class=\"normal\">{Backup_Inform}</div><div class=\"highlight\">{Backup_detail}</div>"\
                  f"<div class=\"normal\">{Baseline_Config_Differ}</div><div class=\"highlight\">{Baseline_Config_Difference}</div>"\
                  f"<div class=\"normal\">{Config_Differ}</div><div class=\"highlight\">{Config_Difference}</div>"
        '''
        return content

    #def send_msg(self, Error_Device, Device_List, Baseline_difference, Baseline_different_device, difference, Difference_device):
    def send_msg(self, Error_Device, Device_List, difference, Difference_device):    
        url = "https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token=" + self.token
        header = {
                "Content-Type": "application/json"
        }
        #content= WeChatPub.make_msg(Error_Device, Device_List,Baseline_difference, Baseline_different_device ,difference, Difference_device)
        content= WeChatPub.make_msg(Error_Device, Device_List,difference, Difference_device)
        #print(content)
        form_data = {
            "touser": "20039675",
            "msgtype": "textcard",
            "agentid": 1000027,
            "textcard": {
                "title": "配置备份提醒",
                "description": content,
                "url":"http://172.20.1.213:8080",
                "btntxt":""
            },
            "safe": 0
        }
        rep = self.s.post(url, data=json.dumps(form_data).encode('utf-8'), headers=header)
        print(json.loads(rep.content))
        return json.loads(rep.content)


def main():
    #IOstream.Get_Device_Json("zbx_export_hosts.json")
    Device_List = IOstream.Get_Device_List(Path)
    #print(Device_List)
    Error_Device=[]
    Difference_device = []
    Fail_Device_List = []
    difference = 0
    Baseline_difference = 0
    Baseline_different_device = []
    error = ""
    for device in Device_List:
        print(device)
        try:
            if re.match( r"cisco",device["device_type"]):
                Config_data = NetWork_Connect.getConfig_Cisco(NetWork_Connect,device)
                difference,Difference_device = Config_result.Record(Config_data,difference,Difference_device)
            elif re.match( r"zyxel",device["device_type"]):
                Config_data = NetWork_Connect.getConfig_Zyxel(NetWork_Connect,device)
                difference,Difference_device = Config_result.Record(Config_data,difference,Difference_device) 
            elif re.match( r"zte",device["device_type"]):
                Config_data = NetWork_Connect.getConfig_MyPower(NetWork_Connect,device)
                difference,Difference_device = Config_result.Record(Config_data,difference,Difference_device)
            elif re.match( r"Oring",device["device_type"]):
                Config_data = NetWork_Connect.getConfig_Oring(NetWork_Connect,device)
                difference,Difference_device = Config_result.Record(Config_data,difference,Difference_device)
            elif re.match( r"ruby",device["device_type"]):
                Config_data = NetWork_Connect.getConfig_Rubytech(NetWork_Connect,device)
                difference,Difference_device = Config_result.Record(Config_data,difference,Difference_device)
            elif re.match(r"arista",device["device_type"]):
                Config_data = NetWork_Connect.getConfig_Arista(NetWork_Connect,device)
                difference,Difference_device = Config_result.Record(Config_data,difference,Difference_device)
        except:
            error=error+"Error host:"+device["host"]+"\n"+"Error: "+str(sys.exc_info()[1])+"\n"
            Error_Device.append(device["host"])
    """
    for device in Device_List:
        print(device)
        try:
            if re.match( r"cisco",device["device_type"]):
                Config_data = NetWork_Connect.getConfig_Cisco(NetWork_Connect,device)
                difference,Difference_device,Baseline_difference,Baseline_different_device = Config_result.Record(Config_data,difference,Difference_device,Baseline_difference,Baseline_different_device)
            elif re.match( r"zyxel",device["device_type"]):
                Config_data = NetWork_Connect.getConfig_Zyxel(NetWork_Connect,device)
                difference,Difference_device,Baseline_difference,Baseline_different_device = Config_result.Record(Config_data,difference,Difference_device,Baseline_difference,Baseline_different_device) 
            elif re.match( r"zte",device["device_type"]):
                Config_data = NetWork_Connect.getConfig_MyPower(NetWork_Connect,device)
                difference,Difference_device,Baseline_difference,Baseline_different_device = Config_result.Record(Config_data,difference,Difference_device,Baseline_difference,Baseline_different_device)
            elif re.match( r"Oring",device["device_type"]):
                Config_data = NetWork_Connect.getConfig_Oring(NetWork_Connect,device)
                difference,Difference_device,Baseline_difference,Baseline_different_device = Config_result.Record(Config_data,difference,Difference_device,Baseline_difference,Baseline_different_device)
            elif re.match( r"ruby",device["device_type"]):
                Config_data = NetWork_Connect.getConfig_Rubytech(NetWork_Connect,device)
                difference,Difference_device,Baseline_difference,Baseline_different_device = Config_result.Record(Config_data,difference,Difference_device,Baseline_difference,Baseline_different_device)
            elif re.match(r"arista",device["device_type"]):
                Config_data = NetWork_Connect.getConfig_Arista(NetWork_Connect,device)
                difference,Difference_device,Baseline_difference,Baseline_different_device = Config_result.Record(Config_data,difference,Difference_device,Baseline_difference,Baseline_different_device)
        except:
            error=error+"Error host:"+device["host"]+"\n"+"Error: "+str(sys.exc_info()[1])+"\n"
            Error_Device.append(device["host"])
    """
    wechat = WeChatPub()
    #wechat.send_msg(Error_Device, Device_List, Baseline_difference, Baseline_different_device, difference, Difference_device)
    wechat.send_msg(Error_Device, Device_List, difference, Difference_device)
    timenow = time.strftime("%Y-%m-%d %H:%M:%S",time.localtime())
    log_path = "config.log"
    error_path = "error.log"
    #print(error)
    IOstream.Create_Error_File(error_path,timenow,error)
    IOstream.Create_Config_Log(log_path,timenow,len(Device_List),len(Error_Device),Error_Device,len(Device_List)-len(Error_Device),difference,Difference_device)

if __name__ == "__main__":
    main()
