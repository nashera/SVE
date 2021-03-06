import os
import sys
import subprocess32 as subprocess
sys.path.append('../') #go up one in the modules
import stage_wrapper
import gzip
from stages.utils.CheckVcf import GetCallCount

#function for auto-making svedb stage entries and returning the stage_id
class breakseq(stage_wrapper.Stage_Wrapper):
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
    def run(self,run_id,inputs):
        #workflow is to run through the stage correctly and then check for error handles
        #[1a]get input names and output names setup
        if ('.fa' not in inputs) or ('.bam' not in inputs) or ('out_dir' not in inputs):
            print "ERROR: .fa, .bam, and out_dir are required for genome_strip.py"
            return None
        #will have to figure out output file name handling
        out_exts = self.split_out_exts()
        out_dir = inputs['out_dir'] + '/'
        stripped_name = ''
        if len(inputs['.bam']) == 1: stripped_name = self.strip_path(self.strip_in_ext(inputs['.bam'][0],'.bam'))
        else: stripped_name = 'joint'
        out_names = {'.vcf' :out_dir+stripped_name+'_S'+str(self.stage_id)+out_exts[0]}
        #[2a]build command args

        #build temp directory to work in
        sub_dir = out_dir+stripped_name+'_S'+str(self.stage_id)+'/'
        if not os.path.exists(sub_dir): os.makedirs(sub_dir)

        gff = ''
        if inputs['genome'] == 'hg19': gff  = self.files['BREAKSEQ-HG19']
        elif inputs['genome'] == 'hg38': gff  = self.files['BREAKSEQ-HG38']

        python    = sys.executable
        samtools  = self.tools['SAMTOOLS']
        bwa       = self.tools['BWA']
        breakseq  = self.tools['BREAKSEQ']

        call      = [python,breakseq, '--bwa', bwa, '--samtools', samtools,
                     '--reference', inputs['.fa'], '--work',sub_dir, '--min_span',str(2),'--window', str(500), 
                     '--min_overlap',str(2), '--junction_length',str(1000), '--bams'] + inputs['.bam']

        if 'threads' in inputs: call += ['--nthreads', str(inputs['threads'])]
        if gff != '': call += ['--bplib_gff', gff]

        #[3a]execute the command here----------------------------------------------------
        output,err = '',{}
        try:
            print ("<<<<<<<<<<<<<SVE command>>>>>>>>>>>>>>>\n")
            print (" ".join(call))
            output += subprocess.check_output(' '.join(call),
                                              stderr=subprocess.STDOUT,shell=True,
                                              env={'PYTHONPATH':self.tools['BREAKSEQ_PATH']})
            if os.path.isfile(sub_dir+'breakseq.vcf.gz'):
                with gzip.open(sub_dir+'breakseq.vcf.gz','rb') as in_file:
                    gz_in = in_file.read()
                with open(out_names['.vcf'],'w') as f:
                    f.write(gz_in)
            os.remove(sub_dir)
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
        except Exception as E:
            print('vcf write os/file IO error')
            err['output'] = 'vcf write os/file IO error'
            err['message'] = 'vcf write os/file IO error'
            err['code'] = 1
        print('output:\n'+output)
                                                
        #[3b]check results--------------------------------------------------
        
        if err != {}:
            print err
        if GetCallCount(out_names['.vcf']) > 0:
            print("<<<<<<<<<<<<<breakseq sucessfull>>>>>>>>>>>>>>>\n")
            return out_names['.vcf']   #return a list of names
        else:
            print("<<<<<<<<<<<<<breakseq failure>>>>>>>>>>>>>>>\n")
            return None
        
