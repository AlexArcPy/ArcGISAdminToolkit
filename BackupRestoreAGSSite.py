#-------------------------------------------------------------
# Name:       Backup and/or Restore ArcGIS Server site
# Purpose:    Backs up or restores an ArcGIS Server site. 
#             - Restores an ArcGIS server site from a backup file.
#             - Creates a site if no site has been created, otherwise will overwrite previous site. 
#             - Restores the license
#             - Need to include data in map service OR make sure referenced data is in same place.
#             - The arcgisserver directories need to be in the same file path on the restore server as the backup server.
#             - Does not include map caches
#             - Need to have ArcGIS for Server and ArcGIS web adaptor for IIS installed (if wanting to restore web adaptor).    
# Author:     Shaun Weston (shaun_weston@eagle.co.nz)
# Date Created:    27/01/2014
# Last Updated:    09/02/2014
# Copyright:   (c) Eagle Technology
# ArcGIS Version:   10.2+
# Python Version:   2.7
#--------------------------------

# Import modules and enable data to be overwritten
import os
import sys
import datetime
import json
import smtplib
import httplib
import urllib
import urlparse
import arcpy
arcpy.env.overwriteOutput = True

# Set variables
logging = "true"
logFile = os.path.join(os.path.dirname(__file__), r"Logs\BackupRestoreAGSSite.log")
sendErrorEmail = "false"
emailTo = ""
emailUser = ""
emailPassword = ""
emailSubject = ""
emailMessage = ""
output = None

# Start of main function
def mainFunction(agsServerSite,username,password,backupRestore,backupFolder,backupFile,restoreWebAdaptor,restoreReport): # Get parameters from ArcGIS Desktop tool by seperating by comma e.g. (var1 is 1st parameter,var2 is 2nd parameter,var3 is 3rd parameter)  
    try:
        # Log start
        if (logging == "true") or (sendErrorEmail == "true"):
            loggingFunction(logFile,"start","")

        # --------------------------------------- Start of code --------------------------------------- #        

        # Get the server site details
        protocol, serverName, serverPort, context = splitSiteURL(agsServerSite)

        # If any of the variables are blank
        if (serverName == None or serverPort == None or protocol == None or context == None):
            return -1

        # Add on slash to context if necessary
        if not context.endswith('/'):
            context += '/'

        # Add on admin to context if necessary   
        if not context.endswith('admin/'):
            context += 'admin/'

        # Get token
        token = getToken(username, password, serverName, serverPort, protocol)
        # If site not created created   
        if token == -1:
            # Create new site
            arcpy.AddMessage("Creating site...")
            siteResult = createSite(username,password,serverName, serverPort, protocol)
        else:    
            arcpy.AddMessage("Site already created...")
            
        # If backing up site
        if (backupRestore == "Backup"):
            # Get token
            token = getToken(username, password, serverName, serverPort, protocol)
            # Backup the site
            backupSite(serverName, serverPort, protocol, context, token, backupFolder)           
        # If restoring site
        if (backupRestore == "Restore"):
            # Get token
            token = getToken(username, password, serverName, serverPort, protocol)            
            # Restore the site
            restoreSite(serverName, serverPort, protocol, context, token, backupFile, restoreReport)   

            # If restoring a web adaptor
            if (restoreWebAdaptor == "true"):
                # Get token
                token = getToken(username, password, serverName, serverPort, protocol)
                # Register the web adaptor
                arcpy.AddMessage("Registering the web adaptor...")                
                registerWebAdaptor(serverName, serverPort, protocol, token)            
        # --------------------------------------- End of code --------------------------------------- #  
            
        # If called from gp tool return the arcpy parameter   
        if __name__ == '__main__':
            # Return the output if there is any
            if output:
                arcpy.SetParameterAsText(1, output)
        # Otherwise return the result          
        else:
            # Return the output if there is any
            if output:
                return output      
        # Log end
        if (logging == "true") or (sendErrorEmail == "true"):
            loggingFunction(logFile,"end","")        
        pass
    # If arcpy error
    except arcpy.ExecuteError:
        # Show the message
        arcpy.AddError(arcpy.GetMessages(2))        
        # Log error
        if (logging == "true") or (sendErrorEmail == "true"):
            loggingFunction(logFile,"error",arcpy.GetMessages(2))
    # If python error
    except Exception as e:
        # Show the message
        arcpy.AddError(e.args[0])          
        # Log error
        if (logging == "true") or (sendErrorEmail == "true"):     
            loggingFunction(logFile,"error",e.args[0])
# End of main function


# Start of back up site function
def backupSite(serverName, serverPort, protocol, context, token, backupFolder):
    if (len(str(backupFolder)) > 0):            
        # Get backup url
        backupURL = context + "exportSite"

        # Setup parameters
        backupFolder = backupFolder.decode(sys.stdin.encoding or sys.getdefaultencoding()).encode('utf-8')
        params = urllib.urlencode({'token': token, 'f': 'json', 'location': backupFolder})

        arcpy.AddMessage("Backing up the ArcGIS Server site running at " + serverName + "...")

        try:
            # Post to server
            response, data = postToServer(serverName, serverPort, protocol, backupURL, params)
        except:
            arcpy.AddError("Unable to connect to the ArcGIS Server site on " + serverName + ". Please check if the server is running.")
            # Log error
            if (logging == "true") or (sendErrorEmail == "true"):       
                loggingFunction(logFile,"error","Unable to connect to the ArcGIS Server site on " + serverName + ". Please check if the server is running.")            
            return -1

        # If there is an error
        if (response.status != 200):
            arcpy.AddError("Unable to back up the ArcGIS Server site running at " + serverName)
            arcpy.AddError(str(data))
            # Log error
            if (logging == "true") or (sendErrorEmail == "true"):       
                loggingFunction(logFile,"error","Unable to back up the ArcGIS Server site running at " + serverName)              
            return -1
        
        if (not assertJsonSuccess(data)):
            arcpy.AddError("Unable to back up the ArcGIS Server site running at " + serverName)
            # Log error
            if (logging == "true") or (sendErrorEmail == "true"):       
                loggingFunction(logFile,"error","Unable to back up the ArcGIS Server site running at " + serverName)            
            return -1                    
        # On successful backup
        else:
            dataObject = json.loads(data)
            arcpy.AddMessage("ArcGIS Server site has been successfully backed up and is available at this location: " + dataObject['location'] + "...")
    else:
        arcpy.AddError("Please define a folder for the backup to be exported to.");
        # Log error
        if (logging == "true") or (sendErrorEmail == "true"):       
            loggingFunction(logFile,"error","Please define a folder for the backup to be exported to.")        
# End of back up site function

    
# Start of restore site function
def restoreSite(serverName, serverPort, protocol, context, token, backupFile, restoreReport):
    if (len(str(backupFile)) > 0):
        # Get restore url
        restoreURL = context + "importSite"

        arcpy.AddMessage("Beginning to restore the ArcGIS Server site running on " + serverName + " using the site backup available at: " + backupFile + "...")
        arcpy.AddMessage("This operation can take some time. You will not receive any status messages and will not be able to access the site until the operation is complete...")

        # Setup parameters
        backupFile = backupFile.decode(sys.stdin.encoding or sys.getdefaultencoding()).encode('utf-8')
        params = urllib.urlencode({'token': token, 'f': 'json', 'location': backupFile})

        try:
            # Post to server
            response, data = postToServer(serverName, serverPort, protocol, restoreURL, params)
        except:
            arcpy.AddError("Unable to connect to the ArcGIS Server site on " + serverName + ". Please check if the server is running.")
            # Log error
            if (logging == "true") or (sendErrorEmail == "true"):       
                loggingFunction(logFile,"error","Unable to connect to the ArcGIS Server site on " + serverName + ". Please check if the server is running.")            
            return -1   

        # If there is an error 
        if (response.status != 200):
            arcpy.AddError("The restore of the ArcGIS Server site " + serverName + " failed.")
            arcpy.AddError(str(data))
            # Log error
            if (logging == "true") or (sendErrorEmail == "true"):       
                loggingFunction(logFile,"error","The restore of the ArcGIS Server site " + serverName + " failed.")              
            return -1

        if (not assertJsonSuccess(data)):
            arcpy.AddError("The restore of the ArcGIS Server site " + serverName + " failed.")
            arcpy.AddError(str(data))
            # Log error
            if (logging == "true") or (sendErrorEmail == "true"):       
                loggingFunction(logFile,"error","The restore of the ArcGIS Server site " + serverName + " failed.")               
            return -1                    
        # On successful restore
        else:
            # Convert the http response to JSON object
            dataObject = json.loads(data)
            results = dataObject['result']

            # Message list array                
            msgList = []
            
            restoreOpTime = ''        
            for result in results:
                messages = result['messages']
                # For each message in the results
                for message in messages:
                    if ('Import operation completed in ' in message['message'] and message['level'] == 'INFO' and result['source'] == 'SITE') :
                        # Get message operation time
                        restoreOpTime = message['message']
                        arcpy.AddMessage("ArcGIS Server site has been successfully restored. " + message['message'])
                    else:
                        # Append in messages
                        msgList.append(message['message'])  
            
            # If user wants the report generated from the restore utility to be saved to a file in addition to writing the messages to the console        
            if (len(restoreReport) > 0):
                try:
                    # Open report file
                    reportFile = open(restoreReport, "w")
                    # Write success message
                    reportFile.write("Site has been successfully restored. " + restoreOpTime)
                    reportFile.write("\n\n")
                    # Write other messages if there are any
                    if (len(msgList) > 0):
                        reportFile.write("Below are the messages returned from the restore operation. You should review these messages and update your site configuration as needed:")
                        reportFile.write("\n")
                        reportFile.write("-------------------------------------------------------------------------------------------------------------------------------------")
                        reportFile.write("\n")
                        count = 1
                        for msg in msgList:
                            reportFile.write(str(count)+ "." + msg)
                            reportFile.write("\n\n")
                            count = count + 1
                    reportFile.close()
                    arcpy.AddMessage("A file with the report from the restore utility has been saved at: " + restoreReport) 
                except:
                    arcpy.AddError("Unable to save the report file at: " + restoreReport + " Please verify this location is available.")
                    # Log error
                    if (logging == "true") or (sendErrorEmail == "true"):       
                        loggingFunction(logFile,"error","Unable to save the report file at: " + restoreReport + " Please verify this location is available.")                       
                    return
    else:
        arcpy.AddError("Please define a ArcGIS Server site backup file.");
        # Log error
        if (logging == "true") or (sendErrorEmail == "true"):       
            loggingFunction(logFile,"error","Please define a ArcGIS Server site backup file.")        
# End of restore site function
    

# Start of create site function
def createSite(username, password, serverName, serverPort, protocol):  
    # Set up parameters for the request
    params = urllib.urlencode({'username': username.decode(sys.stdin.encoding or sys.getdefaultencoding()).encode('utf-8'), 'password': password.decode(sys.stdin.encoding or sys.getdefaultencoding()).encode('utf-8'), 'configStoreConnection': '', 'directories': '', 'runAsync': 'false', 'f': 'json'})

    # Construct URL to create a new site
    url = "/arcgis/admin/createNewSite"

    # Post to the server
    try:
        response, data = postToServer(serverName, serverPort, protocol, url, params)
    except:
        arcpy.AddError("Unable to connect to the ArcGIS Server site on " + serverName + ". Please check if the server is running.")
        # Log error
        if (logging == "true") or (sendErrorEmail == "true"):       
            loggingFunction(logFile,"error","Unable to connect to the ArcGIS Server site on " + serverName + ". Please check if the server is running.")                    
        return -1

    # If there is an error creating the site
    if (response.status != 200):
        arcpy.AddError("Error creating site.")
        arcpy.AddError(str(data))
        # Log error
        if (logging == "true") or (sendErrorEmail == "true"):       
            loggingFunction(logFile,"error","Error creating site.")          
        return -1
    if (not assertJsonSuccess(data)):
        return -1
    # On successful creation
    else: 
        dataObject = json.loads(data)

        arcpy.AddMessage("Site created successfully...")
        return     
# End of create site function


# Start of register web adaptor function
def registerWebAdaptor(serverName, serverPort, protocol, token):
    params = urllib.urlencode({'webAdaptorURL': 'http://' + serverName + '/arcgis', 'machineName': serverName, 'isAdminEnabled': 'false', 'token': token, 'f': 'json'})

    # Construct URL to register web adaptor
    url = "/arcgis/admin/system/webadaptors/register"

    # Post to the server
    try:
        response, data = postToServer(serverName, serverPort, protocol, url, params)
    except:
        arcpy.AddError("Unable to connect to the ArcGIS Server site on " + serverName + ". Please check if the server is running.")
        # Log error
        if (logging == "true") or (sendErrorEmail == "true"):       
            loggingFunction(logFile,"error","Unable to connect to the ArcGIS Server site on " + serverName + ". Please check if the server is running.")            
        return -1

    # If there is an error registering web adaptor
    if (response.status != 200):
        arcpy.AddError("Error registering web adaptor.")
        arcpy.AddError(str(data))
        # Log error
        if (logging == "true") or (sendErrorEmail == "true"):       
            loggingFunction(logFile,"error","Error registering web adaptor.")          
        return -1
    if (not assertJsonSuccess(data)):
        arcpy.AddError("Error registering web adaptor. Please check if the server is running and ensure that the username/password provided are correct.")
        # Log error
        if (logging == "true") or (sendErrorEmail == "true"):       
            loggingFunction(logFile,"error","Error registering web adaptor. Please check if the server is running and ensure that the username/password provided are correct.")   
        return -1
    # On successful registration
    else: 
        dataObject = json.loads(data)

        arcpy.AddMessage("Web adaptor registered successfully...")
        return     
# End of register web adaptor function


# Start of get token function
def getToken(username, password, serverName, serverPort, protocol):
    params = urllib.urlencode({'username': username.decode(sys.stdin.encoding or sys.getdefaultencoding()).encode('utf-8'), 'password': password.decode(sys.stdin.encoding or sys.getdefaultencoding()).encode('utf-8'),'client': 'referer','referer':'backuputility','f': 'json'})
           
    # Construct URL to get a token
    url = "/arcgis/tokens/generateToken"
        
    try:
        response, data = postToServer(serverName, serverPort, protocol, url, params)
    except:
        arcpy.AddError("Unable to connect to the ArcGIS Server site on " + serverName + ". Please check if the server is running.")
        # Log error
        if (logging == "true") or (sendErrorEmail == "true"):       
            loggingFunction(logFile,"error","Unable to connect to the ArcGIS Server site on " + serverName + ". Please check if the server is running.")
        return -1    
    # If there is an error getting the token
    if (response.status != 200):
        arcpy.AddError("Error while generating the token.")
        arcpy.AddError(str(data))
        # Log error
        if (logging == "true") or (sendErrorEmail == "true"):       
            loggingFunction(logFile,"error","Error while generating the token.")        
        return -1
    if (not assertJsonSuccess(data)):
        arcpy.AddError("Error while generating the token. Please check if the server is running and ensure that the username/password provided are correct.")
        # Log error
        if (logging == "true") or (sendErrorEmail == "true"):       
            loggingFunction(logFile,"error","Error while generating the token. Please check if the server is running and ensure that the username/password provided are correct.") 
        return -1
    # Token returned
    else:
        # Extract the token from it
        dataObject = json.loads(data)

        # Return the token if available
        if "error" in dataObject:
            arcpy.AddError("Error retrieving token.")
            # Log error
            if (logging == "true") or (sendErrorEmail == "true"):       
                loggingFunction(logFile,"error","Error retrieving token.")             
            return -1        
        else:
            return dataObject['token']
# End of get token function


# Start of HTTP POST request to the server function
def postToServer(serverName, serverPort, protocol, url, params):
    # If on standard port
    if (serverPort == -1 and protocol == 'http'):
        serverPort = 80

    # If on secure port
    if (serverPort == -1 and protocol == 'https'):
        serverPort = 443
        
    if (protocol == 'http'):
        httpConn = httplib.HTTPConnection(serverName, int(serverPort))

    if (protocol == 'https'):
        httpConn = httplib.HTTPSConnection(serverName, int(serverPort))
        
    headers = {"Content-type": "application/x-www-form-urlencoded", "Accept": "text/plain",'referer':'backuputility','referrer':'backuputility'}
     
    # URL encode the resource URL
    url = urllib.quote(url.encode('utf-8'))

    # Build the connection to add the roles to the server
    httpConn.request("POST", url, params, headers) 

    response = httpConn.getresponse()
    data = response.read()

    httpConn.close()

    # Return response
    return (response, data)
# End of HTTP POST request to the server function


# Start of split URL function 
def splitSiteURL(siteURL):
    try:
        serverName = ''
        serverPort = -1
        protocol = 'http'
        context = '/arcgis'
        # Split up the URL provided
        urllist = urlparse.urlsplit(siteURL)
        # Put the URL list into a dictionary
        d = urllist._asdict()

        # Get the server name and port
        serverNameAndPort = d['netloc'].split(":")

        # User did not enter the port number, so we return -1
        if (len(serverNameAndPort) == 1):
            serverName = serverNameAndPort[0]
        else:
            if (len(serverNameAndPort) == 2):
                serverName = serverNameAndPort[0]
                serverPort = serverNameAndPort[1]

        # Get protocol
        if (d['scheme'] is not ''):
            protocol = d['scheme']

        # Get path
        if (d['path'] is not '/' and d['path'] is not ''):
            context = d['path']

        # Return variables
        return protocol, serverName, serverPort, context  
    except:
        arcpy.AddError("The ArcGIS Server site URL should be in the format http(s)://<host>:<port>/arcgis")
        return None, None, None, None
# End of split URL function


# Start of status check JSON object function
def assertJsonSuccess(data):
    obj = json.loads(data)
    if 'status' in obj and obj['status'] == "error":
        if ('messages' in obj):
            errMsgs = obj['messages']
            for errMsg in errMsgs:
                arcpy.AddError(errMsg)
                # Log error
                if (logging == "true") or (sendErrorEmail == "true"):       
                    loggingFunction(logFile,"error",errMsg)                
        return False
    else:
        return True
# End of status check JSON object function


# Start of logging function
def loggingFunction(logFile,result,info):
    #Get the time/date
    setDateTime = datetime.datetime.now()
    currentDateTime = setDateTime.strftime("%d/%m/%Y - %H:%M:%S")
    # Open log file to log message and time/date
    if (result == "start") and (logging == "true"):
        with open(logFile, "a") as f:
            f.write("---" + "\n" + "Process started at " + currentDateTime)
    if (result == "end") and (logging == "true"):
        with open(logFile, "a") as f:
            f.write("\n" + "Process ended at " + currentDateTime + "\n")
            f.write("---" + "\n")
    if (result == "info") and (logging == "true"):
        with open(logFile, "a") as f:
            f.write("\n" + "Info: " + str(info))              
    if (result == "warning") and (logging == "true"):
        with open(logFile, "a") as f:
            f.write("\n" + "Warning: " + str(info))               
    if (result == "error") and (logging == "true"):
        with open(logFile, "a") as f:
            f.write("\n" + "Process ended at " + currentDateTime + "\n")
            f.write("Error: " + str(info) + "\n")        
            f.write("---" + "\n")
    if (result == "error") and (sendErrorEmail == "true"):            
        # Send an email
        arcpy.AddMessage("Sending email...")
        # Server and port information
        smtpserver = smtplib.SMTP("smtp.gmail.com",587) 
        smtpserver.ehlo()
        smtpserver.starttls() 
        smtpserver.ehlo
        # Login with sender email address and password
        smtpserver.login(emailUser, emailPassword)
        # Email content
        header = 'To:' + emailTo + '\n' + 'From: ' + emailUser + '\n' + 'Subject:' + emailSubject + '\n'
        message = header + '\n' + emailMessage + '\n' + '\n' + info
        # Send the email and close the connection
        smtpserver.sendmail(emailUser, emailTo, message)
        smtpserver.close()                
# End of logging function   

# This test allows the script to be used from the operating
# system command prompt (stand-alone), in a Python IDE, 
# as a geoprocessing script tool, or as a module imported in
# another script
if __name__ == '__main__':
    # Arguments are optional - If running from ArcGIS Desktop tool, parameters will be loaded into *argv
    argv = tuple(arcpy.GetParameterAsText(i)
        for i in range(arcpy.GetArgumentCount()))
    mainFunction(*argv)
    
