#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
Copyright (C) 2011-2015 German Aerospace Center DLR
(Deutsches Zentrum fuer Luft- und Raumfahrt e.V.),
Institute of System Dynamics and Control
All rights reserved.

This file is part of PySimulator.

PySimulator is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

PySimulator is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with PySimulator. If not, see www.gnu.org/licenses.
'''

import tempfile
import collections
import FMUInterface2
import FMIDescription2_Connected
import numpy
from enum import Enum
import xml.etree.ElementTree as ET


''' Changed from numpy.uint32 to numpy.long to handle connected FMUs value references
    We append the FMU id with the value reference so we need a bigger data structure.
    We convert the value reference back to numpy.uint32 before calling fmiSet*/fmiGet* functions.
'''
def createfmiReferenceVector(n):
    return (numpy.ndarray(n, numpy.long))
    
def createfmiRealVector(n):
    return (numpy.ndarray(n, numpy.float))

class FMUData:
    def __init__(self):
        self.valueReferences = []
        self.values = []

class FMIVarType(Enum):
    Real = 1
    Integer = 2
    Enumeration = 3
    Boolean = 4
    String = 5

class FMUInterface:
    ''' This class encapsulates the FMU C-Interface
        all fmi* functions are a public interface to the FMU-functions
    '''
    def __init__(self, connectedfmusitems, xml, connectionorder, parent=None, loggingOn=True, preferredFmiType='me',algebraicloop=None):
        ''' Load an FMU-File and start a new instance
            @param fileName: complete path and name of FMU-file (.fmu)
            @type fileName: string
        '''
        self._connections = []
        self._connectionorder = connectionorder
        self.FMUInterfaces = {}
        self.FMUItems = {}
        self.activeFmiType = preferredFmiType  # 'me' or 'cs'
        self.visible = 0

        self._loggingOn = loggingOn
        self._tempDir = tempfile.mkdtemp()
        self.algebraicloop = algebraicloop
        # create FMUInterface objects
        for i in xrange(len(connectedfmusitems)):
            fileName = connectedfmusitems[i]['filename']
            FMUInterfaceObj = FMUInterface2.FMUInterface(fileName, self, loggingOn, preferredFmiType)
            FMUInterfaceObj.instanceName = connectedfmusitems[i]['instancename']
            # assuming we won't get FMUs more than 999.
            self.FMUInterfaces[str(i+1).ljust(3, '0')] = FMUInterfaceObj
            self.FMUItems[FMUInterfaceObj.instanceName] = str(i+1).ljust(3, '0')
        self.description = FMIDescription2_Connected.FMIDescription(self.FMUInterfaces,xml)
        
        ## Get the internaldependencyorder and connection information
        self.internaldependencyorder=self.description.internaldependencyorder
        self.connectioninfo=self.description.connectioninfo
        self.inputvarlist=self.description.inputvarlist
        self.outputvarlist=self.description.outputvarlist
        ## Get the name associated with valuereference
        self.variablename=self.description.ValueReference
        
        # read the xml to know the connections
        rootElement = ET.fromstring(xml)
        for connection in rootElement.iter('connection'):
            self._connections.append({'fromFmuName':connection.get('fromFmuName'), 'fromVariableName':connection.get('fromVariableName'),
                                      'toFmuName':connection.get('toFmuName'), 'toVariableName':connection.get('toVariableName')})

    def createFmiData(self, valueReference, value):
        fmus = {}
        for i in xrange(len(valueReference)):
            key = str(valueReference[i])[:3]
            if fmus.has_key(key):
                fmu = fmus[key]
            else:
                fmu = FMUData()
                fmus[key] = fmu
            fmu.valueReferences.append(str(valueReference[i])[3:])
            if (value is not None):
                fmu.values.append(value[i])
        return fmus

    def makeFmiGetCall(self, fmus, valueReference, fmiVarType):
        statuses = []
        if fmiVarType == FMIVarType.Real:
            values = FMUInterface2.createfmiRealVector(len(valueReference))
        elif fmiVarType == FMIVarType.Integer or fmiVarType == FMIVarType.Enumeration:
            values = FMUInterface2.createfmiIntegerVector(len(valueReference))
        elif fmiVarType == FMIVarType.Boolean:
            values = FMUInterface2.createfmiBooleanVector(len(valueReference))
        elif fmiVarType == FMIVarType.String:
            values = FMUInterface2.createfmiStringVector(len(valueReference))

        for key, fmuData in fmus.iteritems():
            FMUValueReference = numpy.array(map(numpy.uint32, fmuData.valueReferences))
            if self.FMUInterfaces.has_key(key):
                FMUInterfaceObj = self.FMUInterfaces[key]
                if fmiVarType == FMIVarType.Real:
                    status, value = FMUInterfaceObj.fmiGetReal(FMUValueReference)
                elif fmiVarType == FMIVarType.Integer or fmiVarType == FMIVarType.Enumeration:
                    status, value = FMUInterfaceObj.fmiGetInteger(FMUValueReference)
                elif fmiVarType == FMIVarType.Boolean:
                    status, value = FMUInterfaceObj.fmiGetBoolean(FMUValueReference)
                elif fmiVarType == FMIVarType.String:
                    status, value = FMUInterfaceObj.fmiGetString(FMUValueReference)

                # store the value we get from fmiGet* function against correct value reference
                for i in xrange(len(valueReference)):
                    if key == str(valueReference[i])[:3]:
                        for j in xrange(len(FMUValueReference)):
                            if str(FMUValueReference[j]) == str(valueReference[i])[3:]:
                                values[i] = value[j]
                statuses.append(status)
        return statuses, values

    def makeFmiSetCall(self, fmus, fmiVarType):
        status = []
        for key, fmuData in fmus.iteritems():
            FMUValueReference = numpy.array(map(numpy.uint32, fmuData.valueReferences))

            if self.FMUInterfaces.has_key(key):
                FMUInterfaceObj = self.FMUInterfaces[key]
                if fmiVarType == FMIVarType.Real:
                    FMUValue = numpy.array(map(numpy.float, fmuData.values))
                    status.append(FMUInterfaceObj.fmiSetReal(FMUValueReference, FMUValue))
                elif fmiVarType == FMIVarType.Integer or fmiVarType == FMIVarType.Enumeration:
                    FMUValue = numpy.array(map(numpy.int, fmuData.values))
                    status.append(FMUInterfaceObj.fmiSetInteger(FMUValueReference, FMUValue))
                elif fmiVarType == FMIVarType.Boolean:
                    FMUValue = numpy.array(map(numpy.int, fmuData.values))
                    status.append(FMUInterfaceObj.fmiSetBoolean(FMUValueReference, FMUValue))
                elif fmiVarType == FMIVarType.String:
                    FMUValue = numpy.array(map(numpy.str, fmuData.values))
                    status.append(FMUInterfaceObj.fmiSetString(FMUValueReference, FMUValue))

        return status

    def getValue(self, name):
        ''' Returns the values of the variables given in name;
            name is a String.
        '''
        dataType = self.description.scalarVariables[name].type.basicType
        ScalarVariableReferenceVector = createfmiReferenceVector(1)
        ScalarVariableReferenceVector[0] = self.description.scalarVariables[name].valueReference
        if dataType == 'Real':
            status, values = self.fmiGetReal(ScalarVariableReferenceVector)
            return values[0]
        elif dataType == 'Integer' or dataType == 'Enumeration':
            status, values = self.fmiGetInteger(ScalarVariableReferenceVector)
            return values[0]
        elif dataType == 'Boolean':
            status, values = self.fmiGetBoolean(ScalarVariableReferenceVector)
            return values[0]
        elif dataType == 'String':
            status, values = self.fmiGetString(ScalarVariableReferenceVector)
            return values[0]

    def setValue(self, valueName, valueValue):
        ''' set the variable valueName to valueValue
            @param valueName: name of variable to be set
            @type valueName: string
            @param valueValue: new value
            @type valueValue: any type castable to the type of the variable valueName
        '''
        ScalarVariableReferenceVector = createfmiReferenceVector(1)
        ScalarVariableReferenceVector[0] = self.description.scalarVariables[valueName].valueReference
        if self.description.scalarVariables[valueName].type.basicType == 'Real':
            ScalarVariableValueVector = FMUInterface2.createfmiRealVector(1)
            ScalarVariableValueVector[0] = float(valueValue)
            self.fmiSetReal(ScalarVariableReferenceVector, ScalarVariableValueVector)
        elif self.description.scalarVariables[valueName].type.basicType in ['Integer', 'Enumeration']:
            ScalarVariableValueVector = FMUInterface2.createfmiIntegerVector(1)
            ScalarVariableValueVector[0] = int(valueValue)
            self.fmiSetInteger(ScalarVariableReferenceVector, ScalarVariableValueVector)
        elif self.description.scalarVariables[valueName].type.basicType == 'Boolean':
            ScalarVariableValueVector = FMUInterface2.createfmiBooleanVector(1)
            ScalarVariableValueVector[0] = FMUInterface2.fmiTrue if valueValue == 1 else FMUInterface2.fmiFalse
            self.fmiSetBoolean(ScalarVariableReferenceVector, ScalarVariableValueVector)
        elif self.description.scalarVariables[valueName].type.basicType == 'String':
            ScalarVariableValueVector = FMUInterface2.createfmiStringVector(1)
            ScalarVariableValueVector[0] = unicode(valueValue)
            self.fmiSetString(ScalarVariableReferenceVector, ScalarVariableValueVector)

    ''' FMI functions '''
    def fmiInstantiate(self):
        for key, FMUInterfaceObj in self.FMUInterfaces.iteritems():
            FMUInterfaceObj.fmiInstantiate()

    def free(self):
        for key, FMUInterfaceObj in self.FMUInterfaces.iteritems():
            FMUInterfaceObj.free()

    def freeModelInstance(self):
        ''' Call FMU destructor before being destructed. Just cleaning up. '''
        for key, FMUInterfaceObj in self.FMUInterfaces.iteritems():
            FMUInterfaceObj.freeModelInstance()

    def fmiSetupExperiment(self, toleranceDefined, tolerance, startTime, stopTimeDefined, stopTime):
        status = []
        for key, FMUInterfaceObj in self.FMUInterfaces.iteritems():
            status.append(FMUInterfaceObj.fmiSetupExperiment(toleranceDefined, tolerance, startTime, stopTimeDefined, stopTime))
        return max(status)

    def fmiEnterInitializationMode(self):
        status = []
        for key, FMUInterfaceObj in self.FMUInterfaces.iteritems():
            status.append(FMUInterfaceObj.fmiEnterInitializationMode())
        return max(status)                
    
    def fmiExitInitializationMode(self):
        status = []
        for key, FMUInterfaceObj in self.FMUInterfaces.iteritems():
            status.append(FMUInterfaceObj.fmiExitInitializationMode())        
        return max(status)
                
        
    def fmiTerminate(self):
        status = []
        for key, FMUInterfaceObj in self.FMUInterfaces.iteritems():
            status.append(FMUInterfaceObj.fmiTerminate())
        return max(status)
    
    ''' Resolve connection with only external dependency'''    
    # def ResolveSetGet(self):
        # for i in xrange(len(self._connectionorder)):
           # for j in self._connectionorder[i]:
               # for ele in xrange(len(self._connections)):
                    # if self._connections[ele]['fromFmuName'] == j:
                        # fromName = self._connections[ele]['fromFmuName'] + '.' + self._connections[ele]['fromVariableName']                     
                        # valref=self.description.scalarVariables[fromName].valueReference                        
                        # get the fmu key from valuereference
                        # getkey=valref[:3]
                        # get the correct valuereference of the corresponding fmus
                        # getcorrectvalref=valref[3:]
                        # FMUValueReference = numpy.array(map(numpy.uint32,[getcorrectvalref]))
                        # get the correct fmu instance from key to get the value                        
                        # fmu=self.FMUInterfaces[getkey]
                        # status,getval=fmu.fmiGetReal(FMUValueReference)
                        # toName = self._connections[ele]['toFmuName'] + '.' + self._connections[ele]['toVariableName']
                        # self.setValue(toName, getval[0])
                        
    ''' Resolve connection combining  internal and external dependency'''
    def ResolveSetGet(self):
        for order in xrange(len(self.internaldependencyorder)):
               n1=self.internaldependencyorder[order]
               if(len(n1)==1):
                  fromName=n1[0]
                  var2=fromName.split('.')
                  try:
                      tolist=self.connectioninfo[fromName]
                      ## Handling of getvalue has to be constructed in this way as self.getValue function cannot be used here due recursion
                      valref=self.description.scalarVariables[fromName].valueReference                        
                      #print fromName,valref
                      #get the fmu key from valuereference
                      getkey=valref[:3]
                      #get the correct valuereference of the corresponding fmus
                      getcorrectvalref=valref[3:]
                      FMUValueReference = numpy.array(map(numpy.uint32,[getcorrectvalref]))
                      #get the correct fmu instance from key to get the value                        
                      fmu=self.FMUInterfaces[getkey]
                      status,getval=fmu.fmiGetReal(FMUValueReference)
                      for z in xrange(len(tolist)):
                          toName=tolist[z]
                          self.setValue(toName,getval[0])
                  except KeyError as e:
                      pass
                      #print "no output edge available or provided for the variable",fromName                          
               else:
                   #Handling for real time Algebraic loops, to be investigated
                   checkvar={}
                   for k in xrange(len(n1)):
                       fromName=n1[k]
                       var2=fromName.split('.')
                       try:
                          tolist=self.connectioninfo[fromName]
                          #fromValue = self.getValue(fromName)
                          ## Handling of getvalue has to be constructed in this way as self.getValue function cannot be used here due recursion
                          valref=self.description.scalarVariables[fromName].valueReference                        
                          #get the fmu key from valuereference
                          getkey=valref[:3]
                          #get the correct valuereference of the corresponding fmus
                          getcorrectvalref=valref[3:]
                          FMUValueReference = numpy.array(map(numpy.uint32,[getcorrectvalref]))
                          #get the correct fmu instance from key to get the value                        
                          fmu=self.FMUInterfaces[getkey]
                          status,getval=fmu.fmiGetReal(FMUValueReference)
                          for y in xrange(len(tolist)):
                              toName=tolist[y]
                              self.setValue(toName,getval[0])
                       except KeyError as e:
                           pass
                           #print "no output edge available or provided for the variable",fromName 
                       '''
                       if(k==0):
                            #print 'start',fromName,getval
                            xstart=getval[0]
                       if(n1[k]==n1[-1]):
                            #print 'last',fromName,getval
                            finalval=getval[0]
                            #va='335544320'
                            FMUValueReference = numpy.array(map(numpy.uint32,[va]))
                            fmu=self.FMUInterfaces['300']
                            status,getval=fmu.fmiGetReal(FMUValueReference)
                            xnew=getval[0]
                            residual=xstart-xnew
                            #print 'after',n1[0],getval,residual
                            if(residual>1e-3):
                                self.AlgebraicLoopSover(n1,residual,xstart,xnew)'''

    

    def AlgebraicLoopSover(self,loops,residual,xstart,xnew):
        old=xstart
        new=xnew
        #self.setValue(loops[0],xstart)
        count=0
        checklist={}
        while(abs(old-new)>1e-4):         
            for k in xrange(len(loops)):
               fromName=loops[k]
               var2=fromName.split('.')
               try:
                  tolist=self.connectioninfo[fromName]
                  #fromValue = self.getValue(fromName)
                  ## Handling of getvalue has to be constructed in this way as self.getValue function cannot be used here due recursion
                  valref=self.description.scalarVariables[fromName].valueReference                        
                  #get the fmu key from valuereference
                  getkey=valref[:3]
                  #get the correct valuereference of the corresponding fmus
                  getcorrectvalref=valref[3:]
                  FMUValueReference = numpy.array(map(numpy.uint32,[getcorrectvalref]))
                  #get the correct fmu instance from key to get the value                        
                  fmu=self.FMUInterfaces[getkey]
                  status,getval=fmu.fmiGetReal(FMUValueReference)
                  for y in xrange(len(tolist)):
                      toName=tolist[y]
                      self.setValue(toName,getval[0])
               except KeyError as e:
                   pass
               if(k==0):
                    #print '***loopsolver1***',fromName,getval
                    checklist['name']=fmu
                    checklist['ValueReference']=FMUValueReference
                    old=getval[0]                   
               if(loops[k]==loops[-1]):
                    #print 'last',fromName,getval
                    finalvalue=getval[0]
                    # va='335544320'
                    # FMUValueReference = numpy.array(map(numpy.uint32,[va]))
                    # fmu=self.FMUInterfaces['300']
                    fmu=checklist['name']
                    FMUValueReference=checklist['ValueReference']
                    status,getval=fmu.fmiGetReal(FMUValueReference)
                    new=getval[0]
                    residual=old-new
                    #print '***loopsolver2***',count,new,old,residual
            count+=1
            if(count==200):
                print "Failed to converge"
                break
    
    def ResolveSolvedList(self,solvelist):
        for order in xrange(len(solvelist)):
               n1=solvelist[order]
               if(len(n1)==1):
                  fromName=n1[0]
                  var2=fromName.split('.')
                  try:
                      tolist=self.connectioninfo[fromName]
                      ## Handling of getvalue has to be constructed in this way as self.getValue function cannot be used here due recursion
                      valref=self.description.scalarVariables[fromName].valueReference                        
                      #print fromName,valref
                      #get the fmu key from valuereference
                      getkey=valref[:3]
                      #get the correct valuereference of the corresponding fmus
                      getcorrectvalref=valref[3:]
                      FMUValueReference = numpy.array(map(numpy.uint32,[getcorrectvalref]))
                      #get the correct fmu instance from key to get the value                        
                      fmu=self.FMUInterfaces[getkey]
                      status,getval=fmu.fmiGetReal(FMUValueReference)
                      for z in xrange(len(tolist)):
                          toName=tolist[z]
                          self.setValue(toName,getval[0])
                  except KeyError as e:
                      pass
                      #print "no output edge available or provided for the variable",fromName                          
               else:
                   #Handling for real time Algebraic loops, to be investigated
                   checkvar={}
                   for k in xrange(len(n1)):
                       fromName=n1[k]
                       var2=fromName.split('.')
                       try:
                          tolist=self.connectioninfo[fromName]
                          #fromValue = self.getValue(fromName)
                          ## Handling of getvalue has to be constructed in this way as self.getValue function cannot be used here due recursion
                          valref=self.description.scalarVariables[fromName].valueReference                        
                          #get the fmu key from valuereference
                          getkey=valref[:3]
                          #get the correct valuereference of the corresponding fmus
                          getcorrectvalref=valref[3:]
                          FMUValueReference = numpy.array(map(numpy.uint32,[getcorrectvalref]))
                          #get the correct fmu instance from key to get the value                        
                          fmu=self.FMUInterfaces[getkey]
                          status,getval=fmu.fmiGetReal(FMUValueReference)
                          for y in xrange(len(tolist)):
                              toName=tolist[y]
                              self.setValue(toName,getval[0])
                       except KeyError as e:
                           pass
                           #print "no output edge available or provided for the variable",fromName
    
    
    def ResolveValueReferenceConnections(self,solvelist):
        ## This function have to be investigated
        varlist=[]
        ## change valureference to real variable name
        for i in xrange(len(solvelist)):
            varef=solvelist[i]
            varlist.append(self.variablename[str(varef)])
        
        getindex=[]
        for z in xrange(len(varlist)):
            name=varlist[z]
            try:
                ind=[y[0] for y in self.internaldependencyorder].index(name)
                getindex.append(ind)
            except ValueError:
                pass
        
        if(len(getindex)!=0):
            pos=max(getindex)
            dependencylist=self.internaldependencyorder[:pos+1]
        else:
            dependencylist=[]
        
        self.ResolveSolvedList(dependencylist)
        
        
    def fmiGetReal(self, valueReference):
        if (self.activeFmiType=='me'):
            #self.ResolveValueReferenceConnections(valueReference)          
            self.ResolveSetGet()
        fmus = self.createFmiData(valueReference, None)
        statuses, values = self.makeFmiGetCall(fmus, valueReference, FMIVarType.Real)            
        return max(statuses), values

    def fmiGetInteger(self, valueReference):
        if (self.activeFmiType=='me'):
            self.ResolveSetGet()
        fmus = self.createFmiData(valueReference, None)
        statuses, values = self.makeFmiGetCall(fmus, valueReference, FMIVarType.Integer)
        return max(statuses), values

    def fmiGetBoolean(self, valueReference):
        if (self.activeFmiType=='me'):
            self.ResolveSetGet()
        fmus = self.createFmiData(valueReference, None)
        statuses, values = self.makeFmiGetCall(fmus, valueReference, FMIVarType.Boolean)
        return max(statuses), values

    def fmiGetString(self, valueReference):
        if (self.activeFmiType=='me'):
            self.ResolveSetGet()
        fmus = self.createFmiData(valueReference, None)
        statuses, values = self.makeFmiGetCall(fmus, valueReference, FMIVarType.String)
        return max(statuses), values

    def fmiSetReal(self, valueReference, value):
        fmus = self.createFmiData(valueReference, value)
        status = self.makeFmiSetCall(fmus, FMIVarType.Real)
        return max(status)

    def fmiSetInteger(self, valueReference, value):
        fmus = self.createFmiData(valueReference, value)
        status = self.makeFmiSetCall(fmus, FMIVarType.Integer)
        return max(status)

    def fmiSetBoolean(self, valueReference, value):
        fmus = self.createFmiData(valueReference, value)
        status = self.makeFmiSetCall(fmus, FMIVarType.Boolean)
        return max(status)

    def fmiSetString(self, valueReference, value):
        fmus = self.createFmiData(valueReference, value)
        status = self.makeFmiSetCall(fmus, FMIVarType.String)
        return max(status)

    def fmiDoStep(self, currentCommunicationPoint, communicationStepSize, noSetFMUStatePriorToCurrentPoint):
        # resolve connections here
        for i in xrange(len(self._connectionorder)):
            for j in self._connectionorder[i]:
                for ele in xrange(len(self._connections)):
                    if self._connections[ele]['fromFmuName'] == j:
                        fromName = self._connections[ele]['fromFmuName'] + '.' + self._connections[ele]['fromVariableName']
                        fromValue = self.getValue(fromName)
                        toName = self._connections[ele]['toFmuName'] + '.' + self._connections[ele]['toVariableName']
                        self.setValue(toName, fromValue)

        status = []
        for key, FMUInterfaceObj in self.FMUInterfaces.iteritems():
            status.append(FMUInterfaceObj.fmiDoStep(currentCommunicationPoint, communicationStepSize, noSetFMUStatePriorToCurrentPoint))
        return max(status)
     
    ## FMI functions for ModelExchange  ## 
    def fmiSetTime(self,tstart):
        status=[]
        for key, FMUInterfaceObj in self.FMUInterfaces.iteritems():
            status.append(FMUInterfaceObj.fmiSetTime(tstart))                  
        return max(status)
    
    def fmiNewDiscreteStates(self):
        statuses=[]
        eventinfo=[]
        for key, FMUInterfaceObj in self.FMUInterfaces.iteritems():
            status,info=FMUInterfaceObj.fmiNewDiscreteStates()
            statuses.append(status)
            eventinfo.append(info)
        
        newDiscreteStatesNeeded=[]
        terminateSimulation=[]
        nominalsOfContinuousStatesChanged=[]
        valuesOfContinuousStatesChanged=[]
        nextEventTimeDefined=[]
        nextEventTime=[]
        for i in xrange(len(eventinfo)):
             e=eventinfo[i]
             newDiscreteStatesNeeded.append(e.newDiscreteStatesNeeded)
             terminateSimulation.append(e.terminateSimulation)
             nominalsOfContinuousStatesChanged.append(e.nominalsOfContinuousStatesChanged)
             valuesOfContinuousStatesChanged.append(e.valuesOfContinuousStatesChanged)
             nextEventTimeDefined.append(e.nextEventTimeDefined)
             if(e.nextEventTime!=0.0):
                nextEventTime.append(e.nextEventTime)
        
        eventInfo = FMUInterface2.fmiEventInfo()
        eventInfo.newDiscreteStatesNeeded=max(newDiscreteStatesNeeded)
        eventInfo.terminateSimulation=max(terminateSimulation)
        eventInfo.nominalsOfContinuousStatesChanged=max(nominalsOfContinuousStatesChanged)
        eventInfo.valuesOfContinuousStatesChanged=max(valuesOfContinuousStatesChanged)
        eventInfo.nextEventTimeDefined=max(nextEventTimeDefined) 
        
        if(len(nextEventTime)!=0):        
            eventInfo.nextEventTime=min(nextEventTime)
        else:
            eventInfo.nextEventTime=0.0
            
        return max(statuses),eventInfo
        
    def fmiEnterContinuousTimeMode(self):
        status=[]
        for key, FMUInterfaceObj in self.FMUInterfaces.iteritems():
            status.append(FMUInterfaceObj.fmiEnterContinuousTimeMode())
        return max(status)
    
    
    def fmiGetEventIndicators(self):
        values = createfmiRealVector(self.description.numberOfEventIndicators)
        statuses=[]
        evector=[]
        mapvalues=collections.OrderedDict()        
        for order in xrange(len(self.internaldependencyorder)):
            n1=self.internaldependencyorder[order]
            if(len(n1)==1):
                  fromName=n1[0]
                  var2=fromName.split('.')
                  getkey=self.FMUItems[var2[0]]
                  FMUInterfaceObj=self.FMUInterfaces[getkey]
                  try:
                      tolist=self.connectioninfo[fromName]
                      ## Handling of getvalue 
                      valref=self.description.scalarVariables[fromName].valueReference                           
                      #get the correct valuereference of the corresponding fmus
                      getcorrectvalref=valref[3:]
                      FMUValueReference = numpy.array(map(numpy.uint32,[getcorrectvalref]))
                      status,getval=FMUInterfaceObj.fmiGetReal(FMUValueReference)
                      for z in xrange(len(tolist)):
                          toName=tolist[z]
                          self.setValue(toName,getval[0])
                  except KeyError as e:
                      ## print no output edge available for the variable",fromName                  
                      pass
                  if (FMUInterfaceObj.description.numberOfEventIndicators!=0):
                        status,value=FMUInterfaceObj.fmiGetEventIndicators()
                        subval=[]
                        for i in xrange(len(value)):
                            val=value[i]
                            subval.append(val)
                        statuses.append(status)
                        mapvalues[FMUInterfaceObj.instanceName]=subval
        
        for k, v in mapvalues.items():
             val=v
             for i in xrange(len(val)):
                evector.append(val[i])
        
        for z in xrange(len(evector)):
            values[z]=evector[z]
        
        return max(statuses),values 
        
    '''   
    def fmiGetContinuousStates(self):
        values =createfmiRealVector(self.description.numberOfContinuousStates)
        statuses=[]
        svector=[]
        for i in xrange(len(self._connectionorder)):
            name=self._connectionorder[i]
            if(len(name)==1):
                getkey=self.FMUItems[name[0]]
                FMUInterfaceObj=self.FMUInterfaces[getkey]
                if (FMUInterfaceObj.description.numberOfContinuousStates!=0):                   
                    status,value=FMUInterfaceObj.fmiGetContinuousStates()
                    for i in xrange(len(value)):
                        val=value[i]
                        svector.append(val)
                    statuses.append(status)
            else:
                for x in xrange(len(name)):
                    getkey=self.FMUItems[name[x]]
                    FMUInterfaceObj=self.FMUInterfaces[getkey]
                    if (FMUInterfaceObj.description.numberOfContinuousStates!=0):                   
                        status,value=FMUInterfaceObj.fmiGetContinuousStates()
                        for i in xrange(len(value)):
                            val=value[i]
                            svector.append(val)
                        statuses.append(status)                        
        for z in xrange(len(svector)):
            values[z]=svector[z]
            
        return max(statuses),values '''
    
    
    def fmiGetContinuousStates(self):
        values =createfmiRealVector(self.description.numberOfContinuousStates)
        statuses=[]
        svector=[]
        finishedfmus=[]
        for order in xrange(len(self.internaldependencyorder)):
            n1=self.internaldependencyorder[order]
            if(len(n1)==1):
                  fromName=n1[0]
                  var2=fromName.split('.')
                  getkey=self.FMUItems[var2[0]]
                  FMUInterfaceObj=self.FMUInterfaces[getkey]
                  if (FMUInterfaceObj.description.numberOfContinuousStates!=0):
                      if FMUInterfaceObj.instanceName not in finishedfmus:
                        status,value=FMUInterfaceObj.fmiGetContinuousStates()
                        for i in xrange(len(value)):
                            val=value[i]
                            svector.append(val)
                        statuses.append(status)
                        finishedfmus.append(FMUInterfaceObj.instanceName)
        for z in xrange(len(svector)):
            values[z]=svector[z]       
        return max(statuses),values       
   
    def fmiGetDerivatives(self):
        values =createfmiRealVector(self.description.numberOfContinuousStates)
        statuses=[]
        svector=[]
        mapvalues=collections.OrderedDict()
        for order in xrange(len(self.internaldependencyorder)):
            n1=self.internaldependencyorder[order]
            if(len(n1)==1):
                  fromName=n1[0]
                  var2=fromName.split('.')
                  getkey=self.FMUItems[var2[0]]
                  FMUInterfaceObj=self.FMUInterfaces[getkey]
                  try:
                      tolist=self.connectioninfo[fromName]
                      ## Handling of getvalue 
                      valref=self.description.scalarVariables[fromName].valueReference                           
                      #get the correct valuereference of the corresponding fmus
                      getcorrectvalref=valref[3:]
                      FMUValueReference = numpy.array(map(numpy.uint32,[getcorrectvalref]))
                      status,getval=FMUInterfaceObj.fmiGetReal(FMUValueReference)
                      for z in xrange(len(tolist)):
                          toName=tolist[z]
                          self.setValue(toName,getval[0])
                  except KeyError as e:
                      ## print no output edge available for the variable",fromName                                    
                      pass
                  if (FMUInterfaceObj.description.numberOfContinuousStates!=0):
                        status,value=FMUInterfaceObj.fmiGetDerivatives()
                        subval=[]
                        for i in xrange(len(value)):
                            val=value[i]
                            subval.append(val)
                        statuses.append(status)                       
                        mapvalues[FMUInterfaceObj.instanceName]=subval     
            else:
                 ## code to handle realtime ALgebraic loops
                 pass                 
        for k, v in mapvalues.items():
             val=v
             for i in xrange(len(val)):
                svector.append(val[i])
                
        for z in xrange(len(svector)):
            values[z]=svector[z]       
        return max(statuses),values                                   
    
    def fmiSetContinuousStates(self,x):
        status=[]
        c=0
        finishedfmus=[]
        for order in xrange(len(self.internaldependencyorder)):
            n1=self.internaldependencyorder[order]
            if(len(n1)==1):
                  fromName=n1[0]
                  var2=fromName.split('.')
                  getkey=self.FMUItems[var2[0]]
                  FMUInterfaceObj=self.FMUInterfaces[getkey]
                  if (FMUInterfaceObj.description.numberOfContinuousStates!=0):
                    if FMUInterfaceObj.instanceName not in finishedfmus:
                        length=FMUInterfaceObj.description.numberOfContinuousStates
                        getval=x[c:length+c]
                        c=c+length
                        status.append(FMUInterfaceObj.fmiSetContinuousStates(getval))
                        finishedfmus.append(FMUInterfaceObj.instanceName)        
        return max(status)
    
    
    def fmiEnterEventMode(self):
        status=[]
        for key, FMUInterfaceObj in self.FMUInterfaces.iteritems():
            status.append(FMUInterfaceObj.fmiEnterEventMode())        
        return max(status)     
    
   

  
        