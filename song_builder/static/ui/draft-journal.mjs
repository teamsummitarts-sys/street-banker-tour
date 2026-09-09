/** Arrangement-only recovery. Audio has already been uploaded before a clip is committed. */
export class DraftJournal {
  constructor(storage, scope, tabId, validate, now=Date.now) {
    this.storage=storage;this.prefix=`room:draft:v1:${scope}:`;this.tabId=tabId;this.validate=validate;this.now=now;
    if(!scope)throw new Error('Account recovery scope is unavailable.');
  }
  key(projectId){return `${this.prefix}${projectId}:${this.tabId}`;}
  write(project,revision,context={}){
    const value={version:1,project:this.validate(project),revision,context,updatedAt:this.now()};
    const encoded=JSON.stringify(value);
    if(encoded.length>2*1024*1024)throw new Error('This draft exceeds the local recovery limit.');
    this.storage.setItem(this.key(project.id),encoded);
  }
  acknowledge(project){
    const key=this.key(project.id),raw=this.storage.getItem(key);
    if(raw){const entry=JSON.parse(raw);if(JSON.stringify(entry.project)===JSON.stringify(project))this.storage.removeItem(key);}
  }
  pending(projectId,saved){
    const result=[];
    for(let index=0;index<this.storage.length;index++){
      const key=this.storage.key(index);if(!key?.startsWith(`${this.prefix}${projectId}:`))continue;
      try{
        const value=JSON.parse(this.storage.getItem(key));
        if(value.version!==1||!Number.isFinite(value.updatedAt)||!Number.isInteger(value.revision)||value.revision<0)continue;
        value.project=this.validate(value.project);
        if(value.project.id!==projectId||JSON.stringify(value.project)===JSON.stringify(saved))continue;
        result.push({...value,key});
      }catch{/* A damaged draft never replaces the saved arrangement. */}
    }
    return result.sort((a,b)=>b.updatedAt-a.updatedAt);
  }
  remove(key){if(!key.startsWith(this.prefix))throw new Error('Draft belongs to another account.');this.storage.removeItem(key);}
}
