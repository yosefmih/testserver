

frontend
backend
   server
      # receive requests from client 
      # validate/clean up etc 
      # then submit to temporal cloud for processing 
   workers 
     # subscrie to temporal cloud for tasks 
     # execute tasks, save them to s3 
    pipeline_worker
    shared_core 
     