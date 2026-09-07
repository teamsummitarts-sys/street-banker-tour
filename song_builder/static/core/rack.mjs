/** Portable track processing. No network, provider, or source-file writes. */
export const RACK_DEFAULT=Object.freeze({enabled:true,body:0,bite:0,dirt:0,space:0,outputDb:0});
export const RACK_PRESETS=Object.freeze([
  {name:'Clean',detail:'Open and clear',body:0,bite:12,dirt:0,space:8,outputDb:-1},
  {name:'Warm',detail:'Full and close',body:30,bite:-20,dirt:12,space:12,outputDb:-2},
  {name:'Grit',detail:'Driven and forward',body:12,bite:25,dirt:65,space:5,outputDb:-3},
  {name:'Space',detail:'Soft room reflections',body:-10,bite:-12,dirt:0,space:75,outputDb:-2},
].map(p=>Object.freeze({...p,enabled:true})));
export function validateRack(value){
  const keys=Object.keys(RACK_DEFAULT);
  if(!value||typeof value!=='object'||![Object.prototype,null].includes(Object.getPrototypeOf(value))||
    Reflect.ownKeys(value).length!==keys.length||Reflect.ownKeys(value).some(k=>!keys.includes(k)||!Object.hasOwn(Object.getOwnPropertyDescriptor(value,k),'value')))
    throw new TypeError('Rack settings must contain plain, supported controls.');
  if(typeof value.enabled!=='boolean')throw new TypeError('Rack enabled must be true or false.');
  for(const [key,min,max]of [['body',-100,100],['bite',-100,100],['dirt',0,100],['space',0,100],['outputDb',-24,6]]){
    if(typeof value[key]!=='number'||!Number.isFinite(value[key])||value[key]<min||value[key]>max)throw new RangeError(`Rack ${key} must be between ${min} and ${max}.`);
  }
  return {...value};
}
export function presetSettings(preset){const {name,detail,...settings}=preset;return validateRack(settings);}
export function sameRack(a,b){return Boolean(a&&b)&&Object.keys(RACK_DEFAULT).every(key=>a[key]===b[key]);}
// Finite room response allows bounded export pre-roll rather than resetting tails.
export const RACK_PREROLL_SECONDS=1;
const rooms=new WeakMap();
function room(context){
  if(rooms.has(context))return rooms.get(context);
  const length=Math.round(context.sampleRate*.65),buffer=context.createBuffer(2,length,context.sampleRate);
  for(let channel=0;channel<2;channel++){
    const samples=buffer.getChannelData(channel);let seed=0x217cc1b7+channel;
    for(let i=Math.round(context.sampleRate*.012);i<length;i++){
      seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;
      samples[i]=((seed>>>0)/2147483648-1)*Math.exp(-9*i/length)*(1-i/length);
    }
  }
  rooms.set(context,buffer);return buffer;
}
const curve=Float32Array.from({length:4097},(_,i)=>Math.tanh(2*(i/2048-1))/2);
export function createRack(context,settings){
  let current=validateRack(settings);const nodes=[];
  const make=method=>{const node=context[method]();nodes.push(node);return node;};
  const dispose=()=>{for(const node of nodes)try{node.disconnect();}catch{/* already disconnected */}};
  try{
    const input=make('createGain'),output=make('createGain'),original=make('createGain'),processed=make('createGain');
    const body=make('createBiquadFilter'),bite=make('createBiquadFilter');
    body.type='lowshelf';body.frequency.value=220;bite.type='highshelf';bite.frequency.value=2600;
    const clean=make('createGain'),drive=make('createGain'),shape=make('createWaveShaper'),dirt=make('createGain'),blend=make('createGain');
    shape.curve=curve;shape.oversample='2x';
    const convolver=make('createConvolver'),space=make('createGain'),level=make('createGain');convolver.buffer=room(context);
    input.connect(original);original.connect(output);
    input.connect(body);body.connect(bite);bite.connect(clean);clean.connect(blend);
    bite.connect(drive);drive.connect(shape);shape.connect(dirt);dirt.connect(blend);
    blend.connect(level);blend.connect(convolver);convolver.connect(space);space.connect(level);level.connect(processed);processed.connect(output);
    function update(value,immediate=false){
      current=validateRack(value);const amount=current.dirt/100;
      const set=(parameter,value)=>{
        if(immediate)parameter.value=value;
        else {parameter.cancelScheduledValues(context.currentTime);parameter.setTargetAtTime(value,context.currentTime,.012);}
      };
      set(body.gain,current.body*.09);set(bite.gain,current.bite*.09);
      set(clean.gain,1-amount);set(drive.gain,1+amount*4);set(dirt.gain,amount/Math.sqrt(1+amount*4));
      set(space.gain,current.space/100*.6);set(level.gain,10**(current.outputDb/20));
      set(original.gain,current.enabled?0:1);set(processed.gain,current.enabled?1:0);
    }
    update(current,true);return {input,output,nodes,update,dispose};
  }catch(error){dispose();throw error;}
}
