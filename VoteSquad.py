# -*- coding: utf-8 -*-
"""
VoteSquad.py

Description:
    Development of a voter database.
    
Created: Summer 2019
Creator: John.Fay@duke.edu
"""

#%% IMPORTS
import pandas as pd
import geopandas as gpd
import os
import requests
from datetime import datetime

#%% FUNCTIONS
def get_block_features(st_fips,co_fips,output_shapefile,api_key):
    '''Imports census block features for the supplied county FIPS code
    
    Description:
        Extracts 2010 census block features for the provided county into a 
        geodataframe, retrieves race composition attributes, and then joins
        these attributes (population, black population, population 18+, 
        black population 18+, and percentages) to the blocks. 
        
        Census feature data are from 'https://www2.census.gov/geo/tiger/'.
        
        If a shapefile name is provided, the data are saved to that name. Otherwise,
        just the geodataframe is returned.
    
    Args:
        st_fips(str): State FIPS code (e.g. '37')
        co_fips(str): County FIPS code (e.g. '183')
        output_shapefile(str)[optional]: Name to save output shapefile
        api_key(str): Census API key
        
    Returns:
        Geodataframe of census blocks for the county with race data
    '''
    #Pull the state block data for the supplied FIPS code
    print("Downloading blocks for {}; this take a few minutes...".format(st_fips))
    dataURL = 'https://www2.census.gov/geo/tiger/TIGER2010BLKPOPHU/tabblock2010_{}_pophu.zip'.format(st_fips)
    fcStBlocks = gpd.read_file(dataURL)
    
    #Subset county blocks
    print("Subsetting data for County FIPS ".format(co_fips))
    fcCoBlocks = fcStBlocks[fcStBlocks.COUNTYFP10 == co_fips]
    
    #Retrieve block attribute data
    dfAttribs = get_block_attributes(st_fips,co_fips,'',api_key)
    fcCoBlocks =  pd.merge(left=fcCoBlocks,left_on='BLOCKID10',
                           right=dfAttribs,right_on='GEOID10',
                           how='outer')
    
    #If no output name is given, just return the geodataframe
    if output_shapefile == '': return fcCoBlocks
    
    #Otherwise, save to a file
    print("Saving to {}".format(output_shapefile))
    fcCoBlocks.to_file(output_shapefile,filetype='Shapefile')
    
    #Write projection to .prj file
    with open(output_shapefile[:-3]+'prj','w') as outPrj:
        outPrj.write('GEOGCS["GCS_North_American_1983",'+
                     'DATUM["D_North_American_1983",'+
                     'SPHEROID["GRS_1980",6378137.0,298.257222101]],'+
                     'PRIMEM["Greenwich",0.0],'+
                     'UNIT["Degree",0.0174532925199433]]')
    
    #Write metadata  to .txt file
    current_date = datetime.now().strftime("%Y-%m-%d")
    with open(output_shapefile[:-3]+'txt','w') as outTxt:
        outTxt.write('Census block data for FIPS{}{} extracted from\n'.format(st_fips,co_fips) +
                     dataURL + '\n' + 
                     'on {}'.format(current_date)
                     )
        
    #Return the geodataframe
    return fcCoBlocks
        
def get_block_attributes(st_fips,co_fips,output_csv,api_key):
    '''Retrieves race composition data using the Census API
    
    Description: Pulls the following block level data from the 2010 SF1 file:
        P003001 - Total population 
        P003003 - Total Black or African American population
        P010001 - Total population 18 years and older
        P010004 - Total Black/African-American population 18 years or older
    Then compute pct Black and pct Black (18+) columns along with 
    
    Args:
        st_fips(str): State FIPS code (e.g. '37')
        co_fips(str): County FIPS code (e.g. '183')
        output_csv(str): Filename to save data
        api_key(str): Census API key
        
    Returns:
        geodataframe of census blocks for the county
    '''
   #Census API call to get the data for the proivded state/county 
    theURL = 'https://api.census.gov/data/2010/dec/sf1'
    params = {'get':'P003001,P003003,P010001,P010004',
              'for':'block:*',
              'in':'state:{}%county:{}'.format(st_fips,co_fips),
              'key':api_key
         }
    #Send the request and convert the response to JSON format
    print("...downloading data...")
    response = requests.get(theURL,params) 
    response_json = response.json()
    #Convert JSON to pandas dataframe
    print("...cleaning data...")
    dfData = pd.DataFrame(response_json[1:],columns=response_json[0])
    #Convert block data columns to numeric
    floatColumns = ['P003001','P003003','P010001','P010004']
    dfData[floatColumns] = dfData[floatColumns].apply(pd.to_numeric)
    #Combine columns into single GEOID10 attribute
    dfData['GEOID10'] = dfData.state+dfData.county+dfData.tract+dfData.block
    #Compute percentages
    dfData['PctBlack'] = dfData.P003003 / dfData.P003001 * 100
    dfData['PctBlack18'] = dfData.P010004 / dfData.P010001 * 100
    #Set null values to zero
    dfData.fillna(0,inplace=True)
    #Remove GEOID component columns
    dfData.drop(['state','county','tract','block'],axis='columns',inplace=True)
    #Export the relevant columns to a csv file, if a name is given
    if output_csv:
        print("...saving data to {}".format(output_csv))
        dfData.to_csv(output_csv,index=False)
    #Return the dataframe
    return dfData
    
def get_voter_data(data_file, address_file, county_name, out_shapefile):
    '''Creates a geocoded feature class of voters within the selected county.
    
    Description:
        Extracts voter data for the provided county from the NC SBE voter
        registration database (http://dl.ncsbe.gov/data/ncvoter_Statewide.zip), 
        and then "geocodes" the data by joining the registered voter's address
        to SBE's address file (https://dl.ncsbe.gov/index.html?prefix=ShapeFiles/).
        
    Args:
        data_file(str): Path to local, unzipped voter registration database
        address_file(str): Path to local, unzipped address points file
        county_name(str): Name of county to extract
        out_shapefile(str): Name of shapefile in which to save the output
    Returns: 
        geodataframe of addresses
    '''
    #Read in all the data
    print("reading in the voter registration data file...")
    dfAll = pd.read_csv(data_file,
                    usecols=['county_desc','voter_reg_num','res_street_address',
                             'res_city_desc','state_cd','zip_code','race_code',
                             'ethnic_code','gender_code','party_cd','ncid'],
                    sep='\t',
                    encoding = "ISO-8859-1")
    
    #Select records for the provided county name - into a new dataframe
    print("  Selecting records for {} county...".format(county_name))
    dfCounty = dfAll[dfAll['county_desc'] == county_name.upper()].reindex()
    
    #Remove dfAll to free memory
    del(dfAll)
    
    #Drop the county name from the table and set the voter registration # as index
    print("  Tidying data...")
    dfCounty.drop('county_desc',axis=1,inplace=True)
    dfCounty.set_index('voter_reg_num',inplace=True)
    #Drop rows with no address data
    dfCounty.dropna(how='any',inplace=True,
                    subset=['res_street_address','res_city_desc','state_cd','zip_code'])
    #Remove double spaces from the residential address field 
    dfCounty['res_street_address'] = dfCounty['res_street_address'].apply(lambda x: ' '.join(x.split()))
    
    #Read address file into a dataframe
    print("Reading in address file...")
    dfAddresses = pd.read_csv(address_file,
                              usecols=['st_address','city','zip','latitude','longitude'])
    
    #Join coords to dfVoter
    print("Joining address to voter data")
    dfX = pd.merge(left=dfCounty,
                   left_on=['res_street_address','res_city_desc','zip_code'],
                   right=dfAddresses,
                   right_on=['st_address','city','zip'],
                   how='left')
    
    #Convert to geodataframe
    print("Converting to spatial dataframe")
    from shapely.geometry import Point
    geom = [Point(x,y) for x,y in zip(dfX.longitude,dfX.latitude)]
    gdfVoter = gpd.GeoDataFrame(dfX,geometry=geom)
    
    #Save the geodataframe
    if out_shapefile == '': return gdfVoter
    
    #Otherwise, save to a file
    print("Saving to {}".format(out_shapefile))
    gdfVoter.to_file(out_shapefile,filetype='Shapefile')
    
    #Write projection to .prj file
    with open(out_shapefile[:-3]+'prj','w') as outPrj:
        outPrj.write('GEOGCS["GCS_North_American_1983",'+
                     'DATUM["D_North_American_1983",'+
                     'SPHEROID["GRS_1980",6378137.0,298.257222101]],'+
                     'PRIMEM["Greenwich",0.0],'+
                     'UNIT["Degree",0.0174532925199433]]')
    
    #Write metadata  to .txt file
    current_date = datetime.now().strftime("%Y-%m-%d")
    with open(out_shapefile[:-3]+'txt','w') as outTxt:
        outTxt.write('Voter data for {} Co. extracted from\n'.format(county_name) +
                     'NC SBE data on {}'.format(current_date)
                     )
    
    return gdfVoter

def get_address_data(output_folder):
    '''Retrieves the NC SBE Address points file to the folder provided.
    '''
    import requests,zipfile, io, glob
    #See if the file already exists, return if so
    file_list = glob.glob(output_folder+'/**/address_points_sboe.txt',recursive=True)
    if len(file_list) > 0:
        print("Address file already exists")
        return file_list[0]
    #Otherwise retrieve the file from the NC SBE server
    print(" Retrieving address file from NC SBE server...")
    fileURL = 'https://s3.amazonaws.com/dl.ncsbe.gov/ShapeFiles/address_points_sboe.zip'
    r = requests.get(fileURL)
    z = zipfile.ZipFile(io.BytesIO(r.content))
    print(" Unpacking data...")
    z.extractall(output_folder)
    #Get the file path
    state_address_file = glob.glob(output_folder+'/**/address_points_data_format.txt',recursive=True)[0]
    print(" Address data saved to {}".format(state_address_file))
    return state_address_file

def subset_address_data(state_address_file,county_name,output_county_address_file):
    '''Creates a subset of the state datafile and returns the filename.
    '''
    #See if the county file already exists, read in as a dataframe if is
    if os.path.exists(output_county_address_file):
        print(" County file already extracted...")
        return(output_county_address_file)
        
    #Otherwise read the data int a dataframe
    print(" Reading statewide data" )
    columns = ['county_id','county','st_address','city','zip','house_no','half_no','st_pre',
               'st_name','st_type','st_suf','lat_feet','long_feet','latitude', 'longitude']
    dfState = pd.read_csv(state_address_file,sep='\t',dtype='str',
                          header=None,index_col=0, names = columns)
    print("{} records extracted".format(dfState.shape[0]))
    #Extract county data and save to file 
    print(" Extracting records for {} county".format(county_name))
    dfCounty = dfState[dfState.county == county_name.upper()]
    #Save to the file
    print(" Saving to {}".format(output_county_address_file))
    dfCounty.to_csv(output_county_address_file)
    #Return the filename
    return output_county_address_file
    
def get_voter_history_data(state_voter_history_file,county_name,save_filename):
    #Check if the county data has already been created
    if os.path.exists(save_filename):
        print("{} already created.".format(save_filename))
        return pd.read_csv(save_filename)
    #Otherwise, create it
    print("Reading statewide voter history file")
    dfHist = pd.read_csv(state_voter_history_file,sep='\t',
                         usecols=['ncid','county_desc','voter_reg_num','voted_party_cd','election_lbl']
                        )
    print("Extracting county data")
    dfHistCounty = dfHist[dfHist.county_desc == county_name.upper()]
    print("Saving to file")
    dfHistCounty.to_csv(save_filename,index=False)
    return dfHistCounty
    
def summarize_voter_history_data(voter_history_dataframe):
    dfVoteCount = voter_history_dataframe['ncid'].value_counts().reset_index()
    dfVoteCount.dropna(how='any',axis='rows',inplace=True)
    dfVoteCount.columns = ['ncid','elections']
    return dfVoteCount

#%% main
#Set the run time variables
state_fips = '37'
county_fips  = '183'
county_name = 'WAKE'

#Get/set the intermediate filenames
block_shapefile_filename = './scratch/wake_blocks.shp'
county_address_file = './scratch/wake_addresses.csv'
state_voter_reg_file = './data/NCSBE/ncvoter_Statewide.txt'
state_voter_history_file = './data/NCSBE/ncvhis_Statewide.txt'
voter_shapefile_name = './scratch/wake_voters.shp'
voter_history_file = './scratch/wake_history.csv'

#Get the Census API key
censusKey = pd.read_csv('{}/APIkeys.csv'.format(os.environ['localappdata'])).iloc[0,1]

#Get the NC SBE address file
stateAddressData = get_address_data('./data/NCSBE')
countyAddressData = subset_address_data(state_address_file=stateAddressData,
                                        county_name=county_name,
                                        output_county_address_file=county_address_file)

#Get the Census block features and attributes
if os.path.exists(block_shapefile_filename):
    print("Reading block features from {}".format(block_shapefile_filename))
else:
    print("Assembling block features from web resources...")
    gdfBlocks = get_block_features(state_fips,county_fips,block_shapefile_filename,censusKey)

#Get the voter features
if os.path.exists(voter_shapefile_name):
    print("Reading voter features from {}".format(voter_shapefile_name))
    gdfVoter = gpd.read_file(voter_shapefile_name)
else:
    print("Assembling voter features from local files resources...")    
    #Retrieve file
    gdfVoter = get_voter_data(state_voter_reg_file,
                              county_address_file,
                              county_name,
                              voter_shapefile_name)

#%%    
dfVoterHistory = get_voter_history_data(state_voter_history_file,county_name,voter_history_file)
dfVoterSummary = summarize_voter_history_data(dfVoterHistory)
gdfVoteGeo = pd.merge(gdfVoter,dfVoterSummary,how = 'right',left_on='ncid',right_on='ncid')
#%% Spatial overlays

#Join block and precinct values to voter points
#Compute and join voting history to voter points