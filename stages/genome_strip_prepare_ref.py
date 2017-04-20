import csv
import os
import sys
import math
import random
import time
import multiprocessing as mp
import subprocess32 as subprocess
sys.path.append('../') #go up one in the modules
import stage_wrapper
import read_utils as sr

def generate_ploidy(seq_n, seq_l, ploidy_file):
    x_n,y_n = '',''
    for i in range(0,len(seq_n)):
        if seq_n[i] == 'X'or seq_n[i] == 'chrX': x_n,x_l = seq_n[i],seq_l[i]
        if seq_n[i] == 'Y'or seq_n[i] == 'chrY': y_n,y_l = seq_n[i],seq_l[i] 
    doubles = ['*',' *',' *',' *',' 2\n']
    if x_n == '' or y_n == '':
        ploidy = ''.join(doubles)
    else:
        singles = [x_n,' 1 ',str(x_l),' F',' 2\n',
                   x_n,' 1 ',str(x_l),' M',' 1\n',
                   y_n,' 1 ',str(y_l),' F',' 0\n',
                   y_n,' 1 ',str(y_l),' M',' 1\n']
        ploidy = ''.join(singles+doubles)
    with open(ploidy_file,'w') as f:
        print('writing ploidy map file for genomestrip')
        f.write(ploidy) #white space delimited with newline

def generate_rdmask(seq_n, seq_l, rdmask_file):
    rdmask = [['CHR','START','END']]
    for i in range(len(seq_n[0:23])): # TODO: this is for human genome only
        rdmask += [[seq_n[i],'1',str(seq_l[i])]]
    with open(rdmask_file,'w') as csvfile:
        print('writing rdmask for genomestrip')
        csvwriter = csv.writer(csvfile, delimiter='\t')
        for row in rdmask:
            csvwriter.writerow(row)

#default SVE in-stage || dispatch for multi-cores----------------------------------------------------- 
   
#function for auto-making svedb stage entries and returning the stage_id
class genome_strip(stage_wrapper.Stage_Wrapper):
    #path will be where a node should process the data using the in_ext, out_ext
    #stage_id should be pre-registered with db, set to None will require getting
    #a new stage_id from the  db by writing and registering it in the stages table
    def __init__(self,wrapper,dbc,retrieve,upload,params):
        #inheritance of base class stage_wrapper    
        stage_wrapper.Stage_Wrapper.__init__(self,wrapper,dbc,retrieve,upload,params)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        return 0
    
    #override this function in each wrapper...
    #~/software/svtoolkit/lib/...
    def run(self,run_id,inputs):
        
        #[1a]get input names and output names setup
        if '.fa' not in inputs:
            print "ERROR: .fa is required for genome_strip_prepare_ref.py"
            return None

        fa_path = self.strip_name(inputs['.fa'])
        
        #will have to figure out output file name handling
        cascade = self.strip_in_ext(inputs['.fa'],'.fa')
        out_names = {'.dict': cascade + '.dict',
                     '.ploidymap.txt':cascade + '.ploidymap.txt',
                     '.rdmask.bed':cascade + '.rdmask.bed',
                     '.svmask.fasta':cascade + '.svmask.fasta'}

        # Download genome_strip bundle if there is
        if 'genome' in inputs:
            bundle_link, bundle_file, bundle_dir = '', '', ''
            if inputs['genome'] == 'hg19':
                bundle_link = "ftp://ftp.broadinstitute.org/pub/svtoolkit/reference_metadata_bundles/Homo_sapiens_assembly19_12May2015.tar.gz"
                bundle_file = self.tools['SVE_HOME'] + '/data/gs_hg19_bundle_file.tar.gz'
                bundle_dir  = self.tools['SVE_HOME'] + '/data/Homo_sapiens_assembly19'
                out_names['.ploidymap.txt'] = bundle_dir + '/Homo_sapiens_assembly19.ploidymap.txt'
                out_names['.rdmask.bed'] = bundle_dir + '/Homo_sapiens_assembly19.rdmask.bed'
                out_names['.svmask.fasta'] = bundle_dir + '/Homo_sapiens_assembly19.svmask.fasta'
            elif inputs['genome'] == 'hg38':
                bundle_link = "ftp://ftp.broadinstitute.org/pub/svtoolkit/reference_metadata_bundles/Homo_sapiens_assembly38_12Oct2016.tar.gz"
                bundle_file = self.tools['SVE_HOME'] + '/data/gs_hg38_bundle_file.tar.gz'
                bundle_dir  = self.tools['SVE_HOME'] + '/data/Homo_sapiens_assembly38'
                out_names['.ploidymap.txt'] = bundle_dir + '/Homo_sapiens_assembly38.ploidymap.txt'
                out_names['.rdmask.bed'] = bundle_dir + '/Homo_sapiens_assembly38.rdmask.bed'
                out_names['.svmask.fasta'] = bundle_dir + '/Homo_sapiens_assembly38.svmask.fasta'

            if not os.path.exists(bundle_dir):
                if not os.path.isfile(bundle_file):
                    print ("<<<<<<<<<<<<<SVE command>>>>>>>>>>>>>>>\n")
                    download = ['wget', '-O', bundle_file, bundle_link]
                    print (' '.join(download))
                    subprocess.check_output(' '.join(download), stderr=subprocess.STDOUT,shell=True)
                print ("<<<<<<<<<<<<<SVE command>>>>>>>>>>>>>>>\n")
                unzip = ['tar', '-zxvf', bundle_file, '-C', self.tools['SVE_HOME']+'/data/']
                print (' '.join(unzip))
                subprocess.check_output(' '.join(unzip), stderr=subprocess.STDOUT,shell=True)
        #[2a]build command args
        
        #environment variable passing here
        SV_DIR = self.tools['GENOME_STRIP_PATH']
        classpath = SV_DIR+'/lib/SVToolkit.jar:'+SV_DIR+'/lib/gatk/GenomeAnalysisTK.jar:'+SV_DIR+'/lib/gatk/Queue.jar'
        cgm  = 'org.broadinstitute.sv.apps.ComputeGenomeMask'

        #[3] gender_map this is for each sample...       
        
        #self.db_start(run_id,out_names['.fa'])        
        #[3a]execute the command here----------------------------------------------------
        output,err = '',{}
        try:
            if not all([os.path.isfile(inputs['.fa']+'.'+suffix) for suffix in ['amb','ann','bwt','pac','sa','rbwt','rpac','rsa']]):
                indexref  = [self.tools['GENOME_STRIP_PATH'] + '/bwa/bwa', 'index', inputs['.fa']]
                print ("<<<<<<<<<<<<<SVE command>>>>>>>>>>>>>>>\n")
                print (' '.join(indexref))
                output += subprocess.check_output(' '.join(indexref),stderr=subprocess.STDOUT,shell=True)

            if not os.path.isfile(inputs['.fa']+'.fai'):
                faidx     = [self.tools['SAMTOOLS'],'faidx',inputs['.fa']]
                print ("<<<<<<<<<<<<<SVE command>>>>>>>>>>>>>>>\n")
                print (' '.join(faidx))
                output += subprocess.check_output(' '.join(faidx),stderr=subprocess.STDOUT,shell=True)

            if not os.path.isfile(out_names['.dict']):
                dictbuild = [self.tools['JAVA-1.8'], '-jar', self.tools['PICARD'], 'CreateSequenceDictionary', 'R='+inputs['.fa'], 'O='+out_names['.dict']]
                print ("<<<<<<<<<<<<<SVE command>>>>>>>>>>>>>>>\n")
                print (' '.join(dictbuild))
                output += subprocess.check_output(' '.join(dictbuild),stderr=subprocess.STDOUT,shell=True)

            if not os.path.isfile(out_names['.svmask.fasta']):
                LD_LIB = self.tools['GENOME_STRIP_PATH']+'/bwa'
                if os.environ.has_key('LD_LIBRARY_PATH'):
                     LD_LIB += ':'+os.environ['LD_LIBRARY_PATH']
                svmask    = [self.tools['JAVA-1.8'], '-cp', classpath, cgm, '-R', inputs['.fa'], '-O', out_names['.svmask.fasta'], '-readLength',str(100)]
                print ("<<<<<<<<<<<<<SVE command>>>>>>>>>>>>>>>\n")
                print (' '.join(svmask))
                output += subprocess.check_output(' '.join(svmask),stderr=subprocess.STDOUT,shell=True,
                                                 env={'LD_LIBRARY_PATH':LD_LIB})

            if not os.path.isfile(out_names['.ploidymap.txt']) or not os.path.isfile(out_names['.rdmask.bed']):
                seq_n = sr.get_fasta_seq_names(inputs['.fa']) #assume last two are sex chroms
                seq_l = sr.get_fasta_seq_lens(inputs['.fa'])  #get the lens here
                if not os.path.isfile(out_names['.ploidymap.txt']): generate_ploidy(seq_n, seq_l, out_names['.ploidymap.txt'])
                if not os.path.isfile(out_names['.rdmask.bed']): generate_rdmask(seq_n, seq_l, out_names['.rdmask.bed'])
                 
            
        #catch all errors that arise under normal call behavior
        except subprocess.CalledProcessError as E:
            print('call error: '+E.output)        #what you would see in the term
            err['output'] = E.output
            #the python exception issues (shouldn't have any...
            print('message: '+E.message)          #?? empty
            err['message'] = E.message
            #return codes used for failure....
            print('code: '+str(E.returncode))     #return 1 for a fail in art?
            err['code'] = E.returncode
        except OSError as E:
            print('os error: '+E.strerror)        #what you would see in the term
            err['output'] = E.strerror
            #the python exception issues (shouldn't have any...
            print('message: '+E.message)          #?? empty
            err['message'] = E.message
            #the error num
            print('code: '+str(E.errno))
            err['code'] = E.errno
        print('output:\n'+output)
       
        #[3b]check results--------------------------------------------------
        if err == {}:
            #self.db_stop(run_id,{'output':output},'',True)
            results = {'.svmask.fasta':out_names['.svmask.fasta'],
                       '.ploidymap.txt':out_names['.ploidymap.txt'],
                       '.rdmask.bed':out_names['.rdmask.bed']}
            #for i in results: print i
            if all([os.path.isfile(r) for key,r in results.iteritems()]):
                print("<<<<<<<<<<<<<genome_strip_prepare_ref sucessfull>>>>>>>>>>>>>>>\n")
                return results   #return a list of names
            else:
                print("<<<<<<<<<<<<<genome_strip_prepare_ref failure>>>>>>>>>>>>>>>\n")
                return None
        else:
            #self.db_stop(run_id,{'output':output},err['message'],False)
            return None
