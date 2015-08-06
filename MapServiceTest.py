#-------------------------------------------------------------
# Name:       Map Service Test
# Purpose:    Runs a configurable query against a map service and produces a report on it's performance.
# Author:     Shaun Weston (shaun_weston@eagle.co.nz)
# Date Created:    05/08/2015
# Last Updated:    06/08/2015
# Copyright:   (c) Eagle Technology
# ArcGIS Version:   10.3+
# Python Version:   2.7
#--------------------------------

# Import modules
import os
import sys
import logging
import smtplib
import arcpy
import string
import urllib2
import time
import json

# Enable data to be overwritten
arcpy.env.overwriteOutput = True

# Set global variables
enableLogging = "false" # Use logger.info("Example..."), logger.warning("Example..."), logger.error("Example...")
logFile = "" # os.path.join(os.path.dirname(__file__), "Example.log")
sendErrorEmail = "false"
emailTo = ""
emailUser = ""
emailPassword = ""
emailSubject = ""
emailMessage = ""
enableProxy = "false"
requestProtocol = "http" # http or https
proxyURL = ""
output = None

# Start of main function
def mainFunction(mapService,boundingBox,cached,scales,imageFormat,csvFile): # Get parameters from ArcGIS Desktop tool by seperating by comma e.g. (var1 is 1st parameter,var2 is 2nd parameter,var3 is 3rd parameter)  
    try:
        # --------------------------------------- Start of code --------------------------------------- #
        # Set constant variables
        dpi = 96
        ImageHeight = 1280
        ImageWidth = 768

        # Seperate out XY coordinates
        boundingBox = boundingBox.split(" ")

        # Get the image format
        if (imageFormat == "PNG"):
            imageFormat = "png"
        if (imageFormat == "JPG"):
            imageFormat = "jpg"            
            
        # Cached map service
        if (cached == "true"):
            # Setup the query
            urlQuery = mapService + "?f=json";
                
            # Make the query to the map service
            try:
                response = urllib2.urlopen(urlQuery).read()
            except urllib2.URLError, error:
                arcpy.AddError(error)
                # Logging
                if (enableLogging == "true"):
                    logger.error(error)                    
                sys.exit()

            dataObject = json.loads(response)
            scales = ""

            # Open text file and write header line       
            summaryFile = open(csvFile, "w")        
            header = "Scale,Number of Tiles,Draw Time (Seconds)\n"
            summaryFile.write(header)
         
            # If the map service is cached
            if "tileInfo" in dataObject:               
                # Get the tile info
                tileInfo = dataObject['tileInfo']
                tileHeight = tileInfo['rows']
                tileWidth = tileInfo['cols']
                tileOriginX = tileInfo['origin']['x']
                tileOriginY = tileInfo['origin']['y']
                dpi = tileInfo['dpi']

                # Get the centre point of the bounding box
                searchPointX = (float(boundingBox[0]) + float(boundingBox[2]))/2
                searchPointY = (float(boundingBox[1]) + float(boundingBox[3]))/2
                
                # Iterate through the levels
                for level in tileInfo['lods']:
                    thisLevel = level['level']
                    thisScale = level['scale']
                    thisResolution = level['resolution']
                    
                    # Dividing image width by DPI to get it in inches
                    imgWidthInInch = ImageWidth / dpi;
                    imgHeightInInch = ImageHeight / dpi;

                    # Converting inch to metre (assume the map is in meter)
                    imgWidthInMapUnit = imgWidthInInch * 0.0254;
                    imgHeightInMapUnit = imgHeightInInch * 0.0254;

                    # Calculating half of maps height & width at the specific scale
                    halfX = (imgWidthInMapUnit * thisScale) / 2;
                    halfY = (imgHeightInMapUnit * thisScale) / 2;

                    # Setup the extent
                    XMin = searchPointX - halfX
                    XMax = searchPointX + halfX
                    YMin = searchPointY - halfY
                    YMax = searchPointY + halfY

                    # Get the tile info - Top left
                    topLeftPointX = XMin
                    topLeftPointY = YMax
                    # Get the tile info - Bottom right
                    bottomRightPointX = XMax
                    bottomRightPointY = YMin
                    
                    # Find the tile row and column - Top left
                    topLeftTileRow = int((float(tileOriginY) - float(topLeftPointY)) / (float(thisResolution) * float(tileHeight)))        
                    topLeftTileColumn = int((float(topLeftPointX) - float(tileOriginX)) / (float(thisResolution) * float(tileWidth)))
                    # Find the tile row and column - Bottom right
                    bottomRightTileRow = int((float(tileOriginY) - float(bottomRightPointY)) / (float(thisResolution) * float(tileHeight)))        
                    bottomRightTileColumn = int((float(bottomRightPointX) - float(tileOriginX)) / (float(thisResolution) * float(tileWidth)))

                    # Return all the tiles in between
                    tileCount = 0
                    totalDownloadTime = 0
                    column = topLeftTileColumn
                    while (column < bottomRightTileColumn):
                        row = topLeftTileRow
                        while (row < bottomRightTileRow):
                            urlQuery = mapService + "/tile/" + str(thisLevel) + "/" + str(row) + "/" + str(column);

                            # Make the query to download the image
                            try:
                                startTime = time.time()
                                response = urllib2.urlopen(urlQuery).read()
                            except urllib2.URLError, error:
                                arcpy.AddError(error)
                                # Logging
                                if (enableLogging == "true"):
                                    logger.error(error)                    
                                sys.exit()

                            endTime = time.time()
                            downloadTime = endTime - startTime                            
                            totalDownloadTime = round(totalDownloadTime + downloadTime,4)

                            # Set the file path
                            file = os.path.join(arcpy.env.scratchFolder, "MapService_" + str(thisScale) + "_" + str(row) + "_" + str(column) + "." + str(imageFormat))

                            # Open the file for writing
                            responseImage = open(file, "wb")

                            # Read from request while writing to file
                            responseImage.write(response)
                            responseImage.close()
                
                            tileCount = tileCount + 1
                            row = row + 1
                        column = column + 1

                    arcpy.AddMessage("1:" + str(thisScale) + " draw time - " + str(totalDownloadTime))
                    
                    # Construct and write the comma-separated line      
                    serviceLine = str(thisScale) + "," + str(tileCount) + "," + str(totalDownloadTime) + "\n"
                    summaryFile.write(serviceLine)

            summaryFile.close()                                       
        # Dynamic map service
        else:
            # If a string, convert to array for scales
            if isinstance(scales, basestring):
                scales = string.split(scales, ";")
            
            # Open text file and write header line       
            summaryFile = open(csvFile, "w")        
            header = "Scale,Draw Time (Seconds)\n"
            summaryFile.write(header)

            # For each scale specified
            for scale in scales:
                # Setup the query
                urlQuery = mapService + "/export?f=image&dpi=" + str(dpi);
                urlQuery = urlQuery + "&format=" + str(imageFormat)            
                urlQuery = urlQuery + "&size=" + str(ImageHeight) + "," + str(ImageWidth)
                urlQuery = urlQuery + "&mapScale=" + str(scale)
                urlQuery = urlQuery + "&bbox=" + str(boundingBox[0]) + "," + str(boundingBox[1]) + "," + str(boundingBox[2]) + "," + str(boundingBox[3])

                # Make the query to download the image
                try:
                    startTime = time.time()
                    response = urllib2.urlopen(urlQuery).read()
                except urllib2.URLError, error:
                    arcpy.AddError(error)
                    # Logging
                    if (enableLogging == "true"):
                        logger.error(error)                    
                    sys.exit()

                endTime = time.time()
                downloadTime = round(endTime - startTime,4)
                arcpy.AddMessage("1:" + str(scale) + " draw time - " + str(downloadTime))

                # Construct and write the comma-separated line         
                serviceLine = str(scale) + "," + str(downloadTime) + "\n"
                summaryFile.write(serviceLine)
                
                # Set the file path
                file = os.path.join(arcpy.env.scratchFolder, "MapService_" + str(scale) + "." + str(imageFormat))
                
                # Open the file for writing
                responseImage = open(file, "wb")

                # Read from request while writing to file
                responseImage.write(response)
                responseImage.close()
            
            summaryFile.close()

        arcpy.AddMessage("Downloaded images location - " + arcpy.env.scratchFolder)
                
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
        # Logging
        if (enableLogging == "true"):
            # Log end of process
            logger.info("Process ended.")
            # Remove file handler and close log file            
            logging.FileHandler.close(logMessage)
            logger.removeHandler(logMessage)
        pass
    # If arcpy error
    except arcpy.ExecuteError:           
        # Build and show the error message
        errorMessage = arcpy.GetMessages(2)   
        arcpy.AddError(errorMessage)           
        # Logging
        if (enableLogging == "true"):
            # Log error          
            logger.error(errorMessage)
            # Log end of process
            logger.info("Process ended.")            
            # Remove file handler and close log file
            logging.FileHandler.close(logMessage)
            logger.removeHandler(logMessage)
        if (sendErrorEmail == "true"):
            # Send email
            sendEmail(errorMessage)
    # If python error
    except Exception as e:
        errorMessage = ""
        # Build and show the error message
        for i in range(len(e.args)):
            if (i == 0):
                errorMessage = unicode(e.args[i]).encode('utf-8')
            else:
                errorMessage = errorMessage + " " + unicode(e.args[i]).encode('utf-8')
        arcpy.AddError(errorMessage)              
        # Logging
        if (enableLogging == "true"):
            # Log error            
            logger.error(errorMessage)
            # Log end of process
            logger.info("Process ended.")            
            # Remove file handler and close log file
            logging.FileHandler.close(logMessage)
            logger.removeHandler(logMessage)
        if (sendErrorEmail == "true"):
            # Send email
            sendEmail(errorMessage)            
# End of main function


# Start of set logging function
def setLogging(logFile):
    # Create a logger
    logger = logging.getLogger(os.path.basename(__file__))
    logger.setLevel(logging.DEBUG)
    # Setup log message handler
    logMessage = logging.FileHandler(logFile)
    # Setup the log formatting
    logFormat = logging.Formatter("%(asctime)s: %(levelname)s - %(message)s", "%d/%m/%Y - %H:%M:%S")
    # Add formatter to log message handler
    logMessage.setFormatter(logFormat)
    # Add log message handler to logger
    logger.addHandler(logMessage) 

    return logger, logMessage               
# End of set logging function


# Start of send email function
def sendEmail(message):
    # Send an email
    arcpy.AddMessage("Sending email...")
    # Server and port information
    smtpServer = smtplib.SMTP("smtp.gmail.com",587) 
    smtpServer.ehlo()
    smtpServer.starttls() 
    smtpServer.ehlo
    # Login with sender email address and password
    smtpServer.login(emailUser, emailPassword)
    # Email content
    header = 'To:' + emailTo + '\n' + 'From: ' + emailUser + '\n' + 'Subject:' + emailSubject + '\n'
    body = header + '\n' + emailMessage + '\n' + '\n' + message
    # Send the email and close the connection
    smtpServer.sendmail(emailUser, emailTo, body)    
# End of send email function


# This test allows the script to be used from the operating
# system command prompt (stand-alone), in a Python IDE, 
# as a geoprocessing script tool, or as a module imported in
# another script
if __name__ == '__main__':
    # Arguments are optional - If running from ArcGIS Desktop tool, parameters will be loaded into *argv
    argv = tuple(arcpy.GetParameterAsText(i)
        for i in range(arcpy.GetArgumentCount()))
    # Logging
    if (enableLogging == "true"):
        # Setup logging
        logger, logMessage = setLogging(logFile)
        # Log start of process
        logger.info("Process started.")
    # Setup the use of a proxy for requests
    if (enableProxy == "true"):
        # Setup the proxy
        proxy = urllib2.ProxyHandler({requestProtocol : proxyURL})
        openURL = urllib2.build_opener(proxy)
        # Install the proxy
        urllib2.install_opener(openURL)
    mainFunction(*argv)
    
